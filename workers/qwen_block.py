#!/usr/bin/env python3
"""Qwen agents (Ollama, local) work on the functions of studio blocks of any game.

    python workers/qwen_block.py --project <game dir> --blocks L1-01003,L1-01004 [--agents 4] [--minutes 5] [--max 0]

Generic version of rayman-rr/tools/qwen_auto.py, with several agents at once. Each agent takes the next unmatched
function that has a starting draft (build/auto/near/, auto_match cache, build/drafts/) and asks the model to
rewrite it until the project's probe_compiler.py says MATCH. Each request is made to give several tries, because
reading the prompt is the slow part (qwen3.5 serves one request at a time):
  - several versions per answer (--variants), all compiled in parallel; the best one is the base of the next request;
  - small functions (--group-size) go by batches of neighbours (--group) in one request;
  - big functions (--patch-size / --patch-lines) get SEARCH/REPLACE edits instead of the whole file (less to write).
Agents never touch the project: matches go to one
integrator, which adds them in batches (src/auto/ + delinks.txt, clang-format), runs `match.py verify`, and
commits (+ pushes) only if it passes; a failing batch is retried one function at a time.
Ollama answers N requests at once only if it was started with OLLAMA_NUM_PARALLEL >= N.
Create <project>/build/qwen_auto/STOP to stop: agents finish their current function, the integrator flushes.
"""
import argparse
import difflib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True, type=Path)
ap.add_argument("--blocks", "--block", dest="blocks", required=True, help="block ids, comma separated")
ap.add_argument("--model", default="qwen9-ctx")
ap.add_argument("--minutes", type=float, default=5.0, help="time limit per function")
ap.add_argument("--agents", type=int, default=1, help="functions worked on at the same time")
ap.add_argument("--max", type=int, default=0, help="at most this many functions (0 = all)")
ap.add_argument("--batch", type=int, default=10, help="matches verified together")
ap.add_argument("--variants", type=int, default=4, help="versions asked in one answer (all compiled in parallel)")
ap.add_argument("--group", type=int, default=6, help="small functions sent in one request (1 = never batch)")
ap.add_argument("--group-size", type=int, default=64, help="functions up to this many bytes go by batches")
ap.add_argument("--group-variants", type=int, default=2, help="versions per function in a batch answer")
ap.add_argument("--patch-size", type=int, default=400, help="functions from this many bytes get edits, not whole files")
ap.add_argument("--patch-lines", type=int, default=60, help="... or whose C has this many lines")
ap.add_argument("--max-tokens", type=int, default=8192, help="cap of one answer")
ap.add_argument("--compile-jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2), help="compilers at once")
ap.add_argument("--no-push", action="store_true")
ap.add_argument("--no-neighbours", action="store_true",
                help="after a match, do not retry its callers / callees with auto_match (clones are always made)")
args = ap.parse_args()
BLOCKS = [b.strip() for b in args.blocks.split(",") if b.strip()]
for _stream in (sys.stdout, sys.stderr):  # Windows consoles (cp932...) cannot print every message (Ollama errors)
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
_log_lock = threading.Lock()

ROOT = args.project.resolve()
sys.path.insert(0, str(ROOT / "tools"))
VERSION = next(p.name for p in sorted((ROOT / "config").iterdir()) if (p / "arm9" / "symbols.txt").exists())
WORK = ROOT / "build" / "qwen_auto"
WORK.mkdir(parents=True, exist_ok=True)
STOP = WORK / "STOP"
LOG = WORK / "log.txt"
FLAGS = "-O4,p"

RULES = """You fix C code for a matching decompilation (Nintendo DS, Metrowerks mwccarm, ARM, -O4,p).
You receive a C file and the ARM disassembly of the ORIGINAL function (TARGET) next to the one your code produces
(CANDIDATE); lines marked * differ. Rewrite the C so that the compiled code becomes identical.
Allowed changes: loop form (for/while/do-while, *p++ vs index), declaration order, temporaries, types
(s32/u32/s16/u16/s8/u8, signed/unsigned), casts, splitting or merging expressions, returning a value.
Keep the first lines (#define / #include) and the function name. Never make the function static
(the game exports it). ASCII only.
A short context may come first (which library or part of the game the function is in, what it calls, by real name
when known): use it to choose meaningful types and variable names, but the target assembly always decides.
Never give back a file unchanged: every version must change something.
"""
# One request gives several tries: the prompt is read once (qwen3.5 serves one request at a time), the candidates
# are compiled in parallel.
FMT_FULL = """Answer with {n} DIFFERENT complete versions of the C file (each one tries another idea), each in its own
```c code block, and nothing else."""
# Big functions: only the lines to change, far less text to generate than the whole file
FMT_PATCH = """Do not rewrite the whole file. Answer with {n} DIFFERENT versions (each one tries another idea). Each version
starts with a line `### Version <k>` followed by one or more edit blocks:
<<<<<<< SEARCH
lines copied exactly from the file
=======
the new lines
>>>>>>> REPLACE
Example of one version:
### Version 1
<<<<<<< SEARCH
    s32 i = 0;
    while (i < n) {
=======
    s32 i;
    for (i = 0; i < n; i++) {
>>>>>>> REPLACE
Nothing else: no full file, no explanation."""
# Small functions: several of them in one request
FMT_GROUP = """You receive several files, one per function, each under a line `### <function name>`. For EACH function,
answer the line `### <function name>` then {n} DIFFERENT complete versions of its file, each in its own ```c code
block. Nothing else."""


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def log(msg):
    with _log_lock:
        print(msg, flush=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def probe(path, name, addr, profile, show=True):
    cmd = [sys.executable, "tools/probe_compiler.py", str(path), name, str(addr), "--only", profile, f"--flags={FLAGS}"]
    if show:
        cmd.append("--show")
    try:
        out = run(cmd, timeout=180).stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "(probe timeout)"
    last = out.splitlines()[-1] if out else ""
    return last.rstrip().endswith("MATCH"), out


def score(out):
    last = out.strip().splitlines()[-1] if out.strip() else ""
    if last.rstrip().endswith("MATCH"):
        return 0
    m = re.search(r"(\d+)/\d+ diff", last)
    if not m:
        return 10000
    return int(m.group(1)) + (1000 if "(size" in last else 0)


def starting_draft(name):
    for p in (ROOT / "build" / "auto" / "near" / f"{name}.c", ROOT / "build" / "drafts" / f"{name}.c"):
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    cache = ROOT / "build" / "auto" / "cache.jsonl"
    if cache.exists():
        best = None
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)["r"]
            except Exception:
                continue
            if r[0] == name and len(r) > 4 and r[4]:
                best = r[4]
        return best
    return None


CODE_BLOCK = re.compile(r"```[a-zA-Z]*[ \t]*\n.*?```", re.S)


def ask(messages, temp, deadline, blocks=1, num_predict=2048):
    """The model's answer, read as it is written and cut as soon as `blocks` ```c blocks are closed: some models go on
    writing after the code (explanations, another version...) and would use the whole time of the function.
    blocks=0: read until the model stops (patch answers have no fixed number of blocks)."""
    body = json.dumps({"model": args.model, "messages": messages, "stream": True,
                       "options": {"temperature": temp, "num_predict": num_predict}, "think": False}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", body, {"Content-Type": "application/json"})
    text = []
    with urllib.request.urlopen(req, timeout=max(30, deadline - time.time())) as r:
        for line in r:  # one JSON object per line
            if not line.strip():
                continue
            part = json.loads(line)
            text.append(part.get("message", {}).get("content", ""))
            if part.get("done") or time.time() > deadline:
                break
            if blocks and "```" in text[-1] and len(CODE_BLOCK.findall("".join(text))) >= blocks:
                break  # closing the connection stops the generation in Ollama
    return "".join(text)


NO_PARALLEL = {"qwen35"}  # architectures Ollama runs one request at a time ("does not support parallel requests")


def model_runs_in_parallel(model: str) -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/show", json.dumps({"model": model}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            arch = json.loads(r.read()).get("model_info", {}).get("general.architecture", "")
        return arch not in NO_PARALLEL
    except Exception:
        return True


def unstatic(code, name):
    """The original symbol is global: `static` would compile to the same bytes but break the link (local symbol)."""
    return re.sub(rf"(?<!\w)static\s+(?=[^;{{}}]*(?<!\w){re.escape(name)}\s*\()", "", code)


CODEMAP = None
_codemap_lock = threading.Lock()


def code_context(name: str) -> str:
    """Which part of the game the function is in (NitroSDK module, C library, game engine...) and the real names of
    what it calls (tools/codemap.py of the project). Empty if the project has no codemap.py yet."""
    with _codemap_lock:
        if CODEMAP is None:
            _load_codemap()
    if not CODEMAP:
        return ""
    try:
        return CODEMAP.context(name)
    except Exception:
        return ""


def _load_codemap():
    global CODEMAP
    if CODEMAP is None:
        try:
            import codemap
            engine = ""
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
                from dsstudio import games
                studio = games.STUDIOS.get(ROOT.name)
                engine = f"engine of {studio} (the developer of {games.TITLES.get(ROOT.name, ROOT.name)})" if studio else ""
            except Exception:
                pass
            CODEMAP = codemap.CodeMap(engine=engine)
            CODEMAP.callers("")  # reads the disassembly now, under the lock (agents are threads)
        except Exception as e:
            log(f"(pas de contexte de code : {e})")
            CODEMAP = False


class Fn:
    """One function being worked on: its best C so far and what the compiler made of it."""

    def __init__(self, name, size, addr, src):
        self.name, self.size, self.addr = name, size, addr
        self.best, self.out, self.score, self.profile = src, "", 10**6, None
        self.notes, self.context, self.source = [], "", None  # source: the matching C, once found

    @property
    def patch_mode(self) -> bool:
        """Big function: ask for edits instead of the whole file."""
        return self.size >= args.patch_size or self.best.count("\n") >= args.patch_lines

    def message(self, room: int) -> str:
        extra = ("\n\nAlready tried from this file, all worse or equal (do something different):\n" +
                 "\n".join(self.notes[-6:])) if self.notes else ""
        context = f"Context (where this code comes from):\n{self.context}\n\n" if self.context else ""
        return f"{context}File:\n```c\n{self.best}```\n\nResult of this file:\n{self.out[-room:]}{extra}"


COMPILE_POOL = ThreadPoolExecutor(max_workers=max(1, args.compile_jobs))
_variant_seq = [0]
_seq_lock = threading.Lock()


def probe_many(cands: list[tuple["Fn", str, str]]) -> list[tuple[bool, str]]:
    """Compiles [(fn, code, profile)] in parallel (each in its own file): [(match, probe output)]."""
    def one(c):
        fn, code, profile = c
        with _seq_lock:
            _variant_seq[0] += 1
            path = WORK / f"{fn.name}.v{_variant_seq[0]}.c"
        path.write_text(code, encoding="utf-8", newline="\n")
        try:
            return probe(path, fn.name, fn.addr, profile)
        finally:
            path.unlink(missing_ok=True)
    return list(COMPILE_POOL.map(one, cands))


def clean(code: str, name: str) -> str:
    return unstatic("".join(c for c in code if ord(c) < 128), name)


def code_blocks(text: str) -> list[str]:
    """```c blocks, plus a last block left open (answer cut by the token cap) when its braces are balanced."""
    out = re.findall(r"```[a-zA-Z]*[ \t]*\n(.*?)```", text, re.S)
    if text.count("```") % 2:
        tail = text[text.rindex("```"):].split("\n", 1)
        if len(tail) == 2 and tail[1].count("{") and tail[1].count("{") == tail[1].count("}"):
            out.append(tail[1])
    return out


EDIT = re.compile(r"<{5,}\s*SEARCH[ \t]*\n(.*?)\n?={5,}[ \t]*\n(.*?)\n?>{5,}\s*REPLACE", re.S)


def apply_edits(text: str, edits: list[tuple[str, str]]) -> str | None:
    """Applies SEARCH/REPLACE edits; a SEARCH that is not found exactly is looked for line by line ignoring
    indentation. None if one edit cannot be placed."""
    for search, replace in edits:
        if not search.strip():
            return None
        if search in text:
            text = text.replace(search, replace, 1)
            continue
        lines, want = text.split("\n"), [l.strip() for l in search.strip("\n").split("\n")]
        for i in range(len(lines) - len(want) + 1):
            if [l.strip() for l in lines[i:i + len(want)]] == want:
                lines[i:i + len(want)] = replace.split("\n")
                break
        else:
            return None
        text = "\n".join(lines)
    return text


def parse_patches(reply: str, fn: Fn) -> list[str]:
    """Each `### Version k` of a patch answer applied to the best file."""
    parts = re.split(r"^#+\s*Version\b.*$", reply, flags=re.M)
    out = []
    for part in parts:
        edits = EDIT.findall(part.replace("```c", "").replace("```", ""))
        if edits:
            new = apply_edits(fn.best, edits)
            if new is not None:
                out.append(new)
    return out


def parse_group(reply: str, fns: list[Fn]) -> dict[str, list[str]]:
    """{function: [versions]} from an answer for several functions: by `### name` headers, and for blocks outside
    them by the function each block defines."""
    by_name = {f.name: f for f in fns}
    out = {f.name: [] for f in fns}
    pieces = re.split(r"^#+\s*`?(\w+)`?\s*$", reply, flags=re.M)
    loose = pieces[0]
    for k in range(1, len(pieces) - 1, 2):
        if pieces[k] in by_name:
            out[pieces[k]] += code_blocks(pieces[k + 1])
        else:
            loose += pieces[k + 1]
    for block in code_blocks(loose):
        owner = next((n for n in by_name if re.search(rf"\b{re.escape(n)}\s*\([^;{{}}]*\)\s*\{{", block)), None)
        if owner:
            out[owner].append(block)
    return out


def request(fns: list[Fn], temp: float, deadline: float) -> dict[str, list[str]]:
    """One request to the model for these functions: {function: [candidate C files]}."""
    v = max(1, args.variants)
    if len(fns) > 1:
        n = max(1, args.group_variants)
        system = RULES + FMT_GROUP.format(n=n)
        user = "\n\n".join(f"### {f.name}\n{f.message(2500)}" for f in fns)
        blocks, predict = n * len(fns), sum(n * (len(f.best) // 3 + 150) for f in fns)
    elif fns[0].patch_mode:
        # room for the edits, or for one whole file when the model writes that instead
        system, user, blocks = RULES + FMT_PATCH.format(n=v), fns[0].message(6000), 0
        predict = max(700 * v, len(fns[0].best) // 3 + 400)
    else:
        f = fns[0]
        system, user = RULES + FMT_FULL.format(n=v), f.message(6000)
        blocks, predict = v, v * (len(f.best) // 3 + 150)
    reply = ask([{"role": "system", "content": system}, {"role": "user", "content": user}], temp, deadline,
                blocks=blocks, num_predict=max(1024, min(args.max_tokens, predict)))
    try:  # the last raw answer, to see what the model writes when versions go missing
        (WORK / "last_reply.txt").write_text(reply, encoding="utf-8")
    except OSError:
        pass
    if len(fns) > 1:
        found = parse_group(reply, fns)
    elif fns[0].patch_mode:
        found = {fns[0].name: parse_patches(reply, fns[0])}
        if not found[fns[0].name]:  # the model wrote whole files anyway
            found[fns[0].name] = code_blocks(reply)
    else:
        found = {fns[0].name: code_blocks(reply)}
    out = {f.name: list(dict.fromkeys(c for c in (clean(x, f.name) for x in found.get(f.name, []))
                                      if c.strip() and c.strip() != f.best.strip()))[:max(v, args.group_variants)]
           for f in fns}
    raw = sum(len(x) for x in found.values())
    if raw and not any(out.values()):
        log(f"  ({raw} version(s) recue(s), toutes identiques au fichier donne)")
    elif not raw:
        log(f"  (reponse de {len(reply)} caracteres sans bloc de code reconnu : build/qwen_auto/last_reply.txt)")
    return out


def solve(unit: list[Fn]) -> None:
    """Works on one function or a batch of small ones until each matches or the time is out (minutes per function).
    Each request asks for several versions; every version is compiled, the best one becomes the new base."""
    deadline = time.time() + args.minutes * 60 * len(unit)
    pending, empty, rnd = list(unit), 0, 0
    while pending and time.time() < deadline and not STOP.exists():
        rnd += 1
        temp = min(1.0, 0.5 + 0.05 * max(len(f.notes) for f in pending))
        try:
            cands = request(pending, temp, deadline)
        except Exception as e:
            if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError) \
                    or "timed out" in str(e) or "10060" in str(e):  # 10060: Windows timeout, message translated
                log(f"  {', '.join(f.name for f in pending)}: limite de temps atteinte pendant une reponse d'Ollama")
            else:
                log(f"  Ollama ne repond pas ({e}) : lancez Ollama")
            return
        todo = [(f, c, f.profile) for f in pending for c in cands.get(f.name, [])]
        if not todo:
            empty += 1
            log(f"  reponse sans code utilisable ({empty}/3)")
            if empty >= 3:
                return
            continue
        empty = 0
        results = probe_many(todo)
        for f in list(pending):
            mine = [(score(out), ok, code, out) for (g, code, _p), (ok, out) in zip(todo, results) if g is f]
            if not mine:
                continue
            s, ok, code, out = min(mine, key=lambda r: r[0])
            log(f"  {f.name} tour {rnd}: {len(mine)} versions, meilleure {out.strip().splitlines()[-1][-50:] if out.strip() else '?'}"
                f" (avant {f.score})")
            if ok:
                f.source = code
                pending.remove(f)
                continue
            for s2, _ok, c2, _o in mine:
                if s2 >= f.score:
                    changed = [l[1:] for l in difflib.unified_diff(f.best.splitlines(), c2.splitlines(), lineterm="", n=0)
                               if l[:1] in "+-" and l[:3] not in ("+++", "---")][:6]
                    f.notes.append(f"- change {changed} -> score {s2}"[:400])
            if s < f.score:
                f.best, f.out, f.score, f.notes = code, out, s, []


def integrate_and_verify(found):
    """found = [(name, size, addr, source)]. True if the build still matches with all of them."""
    import auto_match as am
    saved = (am.DELINKS.read_bytes(), am.COMPILERS_TXT.read_bytes() if am.COMPILERS_TXT.exists() else b"")
    created = am.integrate(found)
    # Same style as the CI (clang-format), so the commit never breaks the lint check; verify runs after it
    pc = shutil.which("pre-commit")
    if pc:
        run([pc, "run", "clang-format", "--files", *[str(p.relative_to(ROOT)) for p in created]])
    run([sys.executable, "tools/configure.py", VERSION])
    v = run([sys.executable, "tools/match.py", "verify"])
    if v.returncode == 0 and "VERIFY PASSED" in v.stdout:
        return True
    am.DELINKS.write_bytes(saved[0])
    am.COMPILERS_TXT.write_bytes(saved[1])
    for p in created:
        p.unlink(missing_ok=True)
    run([sys.executable, "tools/configure.py", VERSION])
    return False


def commit(found):
    commit_names([f[0] for f in found], "qwen")


def commit_names(names, how):
    run(["git", "add", "src/auto", f"config/{VERSION}"])
    msg = f"Match {len(names)} function(s) ({how}, {', '.join(BLOCKS)})\n\n" + "\n".join(names) + \
        ("\n\nCo-Authored-By: Qwen <noreply@qwen.ai>\n" if how == "qwen" else "\n")
    run(["git", "commit", "-q", "-m", msg, "--", "src/auto", f"config/{VERSION}"])
    if not args.no_push and run(["git", "remote"]).stdout.strip():
        ok = run(["git", "push", "-q", "origin", "HEAD"]).returncode == 0
        log(f"push {'ok' if ok else 'rate (sera refait au prochain commit)'}")


def touch_claims():
    for b in BLOCKS:
        p = ROOT / ".studio" / "claims" / f"{b}.json"
        if p.exists():
            c = json.loads(p.read_text(encoding="utf-8"))
            c["touched"] = time.time()
            p.write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8", newline="\n")


def release_blocks():
    """Qwen is done with its blocks: give them back to the queue (what is left can be taken by someone else)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from dsstudio import blocks as studio_blocks, games as studio_games
        g = studio_games.Game(ROOT)
        for b in BLOCKS:
            r = studio_blocks.release(g, b)
            log(f"bloc {b} rendu a la queue" + (f" ({r.get('error') or r.get('warning')})" if r.get("error") or r.get("warning") else ""))
    except Exception as e:  # never lose the matches because of the queue
        log(f"impossible de rendre les blocs ({e}) : les rendre depuis l'app")


def multiply(names: list[str]) -> list[str]:
    """One AI match is worth more: its clones (same code, or same code with other constants, in this game) are
    matched without the AI (tools/clone_match.py), then the callers and callees of every new match are retried by
    auto_match with the real signatures they now have (tools/auto_match.py --neighbours). Each tool verifies the ROM
    itself. Returns the names they added (committed by the caller)."""
    added = []
    if (ROOT / "tools" / "clone_match.py").exists():
        emit = WORK / "clones.json"
        emit.unlink(missing_ok=True)
        r = run([sys.executable, "tools/clone_match.py", "--sources", ",".join(names), "--emit", str(emit)])
        clones = [tuple(c) for c in json.loads(emit.read_text(encoding="utf-8"))] if emit.exists() else []
        if clones and integrate_and_verify(clones):  # one verify for all the clones of the batch
            added += [c[0] for c in clones]
            log(f"CLONES ({len(clones)}, sans IA) : {', '.join(added)}")
        elif clones:
            log(f"{len(clones)} clones compilent mais VERIFY echoue une fois integres (annules)")
        elif r.returncode:
            log(f"clone_match a echoue : {(r.stdout + r.stderr).strip().splitlines()[-1:]}")
    if not args.no_neighbours:
        before = set(p.stem for p in (ROOT / "src" / "auto").glob("*.c"))
        r = run([sys.executable, "tools/auto_match.py", "--neighbours", ",".join(names + added)])
        new = sorted(set(p.stem for p in (ROOT / "src" / "auto").glob("*.c")) - before)
        if new:
            log(f"VOISINS rematches par auto_match ({len(new)}) : {', '.join(new)}")
            added += new
    return added


class Integrator(threading.Thread):
    """Single writer of the project: batches of matches -> verify -> commit. Failing batches are split."""

    def __init__(self):
        super().__init__(daemon=True)
        self.q, self.won, self.lost, self.extra = queue.Queue(), [], [], []

    def flush(self, batch):
        if integrate_and_verify(batch):
            commit(batch)
            self.won += batch
            log(f"INTEGRE + VERIFY PASSED : {', '.join(f[0] for f in batch)}")
            more = multiply([f[0] for f in batch])
            if more:
                commit_names(more, "clones + neighbours")
                self.extra += more
        elif len(batch) > 1:
            log(f"verify echoue sur un lot de {len(batch)} : reessai une par une")
            for f in batch:
                self.flush([f])
        else:
            self.lost.append(batch[0][0])
            log(f"{batch[0][0]}: match seul mais VERIFY echoue une fois integre (annule)")
        touch_claims()

    def run(self):
        pending = []
        while True:
            try:
                item = self.q.get(timeout=30)
            except queue.Empty:
                item = "tick"
            if item is None:  # end: flush what is left
                if pending:
                    self.flush(pending)
                return
            if item != "tick":
                pending.append(item)
            if pending and (len(pending) >= args.batch or item == "tick"):
                self.flush(pending)
                pending = []


def ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3):
            return True
    except Exception:
        return False


def ensure_ollama(wait: float = 90) -> bool:
    """Starts Ollama when it is not running (the Windows app, else `ollama serve`) and waits until it answers."""
    if ollama_up():
        return True
    import os
    app = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama app.exe")
    exe = shutil.which("ollama") or os.path.join(os.path.dirname(app), "ollama.exe")
    cmd = [app] if os.path.exists(app) else [exe, "serve"] if os.path.exists(exe) else None
    if cmd is None:
        log("Ollama n'est pas installe (https://ollama.com) : impossible de lancer Qwen")
        return False
    log("Ollama ne tourne pas : demarrage...")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=0x00000008 | 0x00000200 if os.name == "nt" else 0)  # detached: outlives this run
    end = time.time() + wait
    while time.time() < end:
        if ollama_up():
            log("Ollama pret")
            return True
        time.sleep(1)
    log("Ollama ne repond toujours pas : lancez-le a la main (application Ollama)")
    return False


def main():
    blocks = {b["id"]: b for b in json.loads((ROOT / ".studio" / "blocks.json").read_text(encoding="utf-8"))["blocks"]}
    missing = [b for b in BLOCKS if b not in blocks]
    if missing:
        sys.exit(f"blocs introuvables dans .studio/blocks.json : {missing}")
    if not ensure_ollama():
        sys.exit(1)
    import auto_match as am
    syms = {}
    for line in am.SYMBOLS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\S+)\s+kind:function\((arm|thumb),size=0x([0-9a-f]+)\).*addr:0x([0-9a-f]+)", line)
        if m:
            syms[m.group(1)] = (int(m.group(4), 16), int(m.group(3), 16), m.group(2))
    covered = am.covered_ranges()
    profiles = [c[0] for c in am.COMPILERS[:2]]
    todo = []
    for b in BLOCKS:
        for name in blocks[b]["functions"]:
            if name not in syms:
                continue
            addr, size, mode = syms[name]
            if mode != "arm" or any(a <= addr < e for a, e in covered):
                continue
            src = starting_draft(name)
            if src:
                todo.append((name, size, addr, src))
    # Worth the most matches first (same code in other games + clones here), then smallest first (they match most
    # often). One function per family of clones: once it matches, clone_match makes the others; the rest of the
    # family comes after, in case the first one fails.
    weight, first = {}, {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from dsstudio import games as studio_games
        g = studio_games.Game(ROOT)
        weight = {r["name"]: studio_games.weight(r) for r in g.functions()}
        first = {n: row.get("first", n) for n, row in studio_games.clone_families(g).items()}
    except Exception as e:
        log(f"(ordre par jumelles indisponible : {e})")
    seen = set()

    def order(t):
        rep = first.get(t[0], t[0])
        later = rep in seen  # another function of the same family comes first
        seen.add(rep)
        return (later, -weight.get(t[0], 0), t[1])
    todo.sort(key=lambda t: t[1])
    todo.sort(key=order)
    if args.max:
        todo = todo[:args.max]
    if args.agents > 1 and not model_runs_in_parallel(args.model):
        # several agents would only queue behind each other, each one getting a fraction of its time limit
        log(f"le modele {args.model} ne repond qu'a une requete a la fois dans Ollama : 1 agent au lieu de {args.agents}")
        args.agents = 1
    # Small functions go by batches of neighbours of similar size (same module of the SDK / engine most of the time):
    # one request for several of them. Each batch starts where the queue order puts its first function.
    units, used = [], set()
    small = [t for t in todo if t[1] <= args.group_size] if args.group > 1 else []
    for t in todo:
        if t[0] in used:
            continue
        unit = [t]
        if t in small:
            near = sorted((u for u in small if u[0] not in used and u is not t),
                          key=lambda u: (abs(u[2] - t[2]) // 0x400, abs(u[1] - t[1]), abs(u[2] - t[2])))
            unit += near[:args.group - 1]
        used.update(u[0] for u in unit)
        units.append(unit)
    log(f"{len(todo)} fonctions avec brouillon en {len(units)} requetes de depart, {args.agents} agent(s), modele "
        f"{args.model}, {args.variants} versions par reponse, blocs {', '.join(BLOCKS)}")
    STOP.unlink(missing_ok=True)
    integ = Integrator()
    integ.start()
    tried = [0]

    def agent(unit):
        if STOP.exists():
            return
        covered = am.covered_ranges()
        fns = [Fn(*t) for t in unit if not any(a <= t[2] < e for a, e in covered)]  # matched meanwhile: skip
        if not fns:
            return
        tried[0] += len(fns)
        starts = probe_many([(f, f.best, p) for f in fns for p in profiles])
        for i, f in enumerate(fns):
            mine = [(score(out), p, out) for p, (_ok, out) in zip(profiles, starts[i * len(profiles):(i + 1) * len(profiles)])]
            f.score, f.profile, f.out = min(mine, key=lambda r: r[0])
            f.context = code_context(f.name)
            if f.score == 0:
                f.source = f.best
            log(f"{f.name} ({f.size} octets, {f.profile}) : depart {f.score} instructions differentes"
                + (" [edits]" if f.patch_mode and len(fns) == 1 else ""))
        if len(fns) > 1:
            log(f"lot de {len(fns)} petites fonctions : {', '.join(f.name for f in fns)}")
        t0 = time.time()
        rest = [f for f in fns if f.source is None]
        if rest:
            solve(rest)
        for f in fns:
            if f.source is None:
                log(f"{f.name}: pas de match ({time.time() - t0:.0f}s)")
                continue
            source = f.source
            if f.profile != profiles[0] and not source.startswith(am.MARKER):
                source = f"{am.MARKER}{f.profile} */\n" + source
            log(f"{f.name}: MATCH en {time.time() - t0:.0f}s -> file d'integration")
            integ.q.put((f.name, f.size, f.addr, source))

    with ThreadPoolExecutor(max_workers=max(1, args.agents)) as ex:
        list(ex.map(agent, units))
    if STOP.exists():
        log("fichier STOP trouve : arret apres les fonctions en cours.")
    integ.q.put(None)
    integ.join()
    release_blocks()
    log(f"fini : {len(integ.won)} nouvelles fonctions sur {tried[0]} essayees"
        + (f", + {len(integ.extra)} sans IA (clones, voisins)" if integ.extra else "")
        + (f" ; rejetees au verify : {', '.join(integ.lost)}" if integ.lost else ""))


if __name__ == "__main__":
    lock_mod = ROOT / "tools" / "pipeline_lock.py"
    if lock_mod.exists():  # same lock as the moulinette / auto_match of this game: never two pipelines at once
        from pipeline_lock import pipeline_lock
        with pipeline_lock("qwen_block", ROOT):
            main()
    else:
        main()
