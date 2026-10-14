#!/usr/bin/env python3
"""Qwen (Ollama, local) works on the functions of one studio block of any game.

    python workers/qwen_block.py --project <game dir> --block L1-01003 [--model qwen9-ctx] [--minutes 5]

Generic version of rayman-rr/tools/qwen_auto.py. For each unmatched function of the block that has a starting
draft (build/auto/near/, auto_match cache, build/drafts/), the model rewrites the C file until the project's
probe_compiler.py says MATCH. Only an exact match is integrated (src/auto/ + delinks.txt), and only if
`match.py verify` passes; otherwise it is rolled back. Each win is committed (and pushed if the game has a remote).
Create <project>/build/qwen_auto/STOP to stop after the current function.
"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--project", required=True, type=Path)
ap.add_argument("--block", required=True)
ap.add_argument("--model", default="qwen9-ctx")
ap.add_argument("--minutes", type=float, default=5.0, help="time limit per function")
ap.add_argument("--no-push", action="store_true")
args = ap.parse_args()

ROOT = args.project.resolve()
sys.path.insert(0, str(ROOT / "tools"))
VERSION = next(p.name for p in sorted((ROOT / "config").iterdir()) if (p / "arm9" / "symbols.txt").exists())
WORK = ROOT / "build" / "qwen_auto"
WORK.mkdir(parents=True, exist_ok=True)
STOP = WORK / "STOP"
LOG = WORK / "log.txt"
FLAGS = "-O4,p"

SYSTEM = """You fix C code for a matching decompilation (Nintendo DS, Metrowerks mwccarm, ARM, -O4,p).
You receive a C file and the ARM disassembly of the ORIGINAL function (TARGET) next to the one your code produces
(CANDIDATE); lines marked * differ. Rewrite the C so that the compiled code becomes identical.
Allowed changes: loop form (for/while/do-while, *p++ vs index), declaration order, temporaries, types
(s32/u32/s16/u16/s8/u8, signed/unsigned), casts, splitting or merging expressions, returning a value.
Keep the first lines (#define / #include) and the function name. ASCII only.
Answer with the COMPLETE new C file in a single ```c code block and nothing else."""


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def log(msg):
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


def ask(messages, temp, deadline):
    body = json.dumps({"model": args.model, "messages": messages, "stream": False,
                       "options": {"temperature": temp}, "think": False}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=max(30, deadline - time.time())) as r:
        return json.loads(r.read())["message"]["content"]


def chat_loop(work, name, addr, profile, out0):
    """Asks for a full new file each time, always from the BEST version so far, with the failed attempts listed."""
    deadline = time.time() + args.minutes * 60
    best, best_out, best_score = work.read_text(encoding="utf-8"), out0, score(out0)
    notes, no_code, attempt = [], 0, 0
    while time.time() < deadline:
        extra = ("\n\nAlready tried from this file, all worse or equal (do something different):\n" +
                 "\n".join(notes[-6:])) if notes else ""
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"File:\n```c\n{best}```\n\nResult of this file:\n{best_out[-6000:]}{extra}"}]
        try:
            reply = ask(msgs, min(1.0, 0.4 + 0.1 * len(notes)), deadline)
        except Exception as e:
            log(f"  Ollama ne repond pas ({e}) : lancez Ollama")
            return False
        m = re.search(r"```[a-zA-Z]*\s*\n(.*?)```", reply, re.S)
        if not m:
            no_code += 1
            if no_code >= 3:
                return False
            continue
        code = "".join(c for c in m.group(1) if ord(c) < 128)
        work.write_text(code, encoding="utf-8", newline="\n")
        attempt += 1
        ok, out = probe(work, name, addr, profile)
        s = score(out)
        log(f"  essai {attempt}: {out.strip().splitlines()[-1][-60:] if out.strip() else '?'} (meilleur {min(s, best_score)})")
        if ok:
            return True
        if s < best_score:
            best, best_out, best_score, notes = code, out, s, []
        else:
            changed = [l[1:] for l in difflib.unified_diff(best.splitlines(), code.splitlines(), lineterm="", n=0)
                       if l[:1] in "+-" and l[:3] not in ("+++", "---")][:6]
            notes.append(f"- change {changed} -> score {s}"[:400])
    work.write_text(best, encoding="utf-8", newline="\n")
    return False


def integrate_and_verify(name, size, addr, source):
    import auto_match as am
    saved = (am.DELINKS.read_bytes(), am.COMPILERS_TXT.read_bytes() if am.COMPILERS_TXT.exists() else b"")
    created = am.integrate([(name, size, addr, source)])
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


def touch_claim():
    p = ROOT / ".studio" / "claims" / f"{args.block}.json"
    if p.exists():
        c = json.loads(p.read_text(encoding="utf-8"))
        c["touched"] = time.time()
        p.write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8", newline="\n")


def main():
    blocks = json.loads((ROOT / ".studio" / "blocks.json").read_text(encoding="utf-8"))["blocks"]
    block = next((b for b in blocks if b["id"] == args.block), None)
    if block is None:
        sys.exit(f"bloc {args.block} introuvable dans .studio/blocks.json")
    import auto_match as am
    syms = {}
    for line in am.SYMBOLS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(\S+)\s+kind:function\((arm|thumb),size=0x([0-9a-f]+)\).*addr:0x([0-9a-f]+)", line)
        if m:
            syms[m.group(1)] = (int(m.group(4), 16), int(m.group(3), 16), m.group(2))
    covered = am.covered_ranges()
    profiles = [c[0] for c in am.COMPILERS[:2]]
    STOP.unlink(missing_ok=True)
    won = tried = 0
    for name in block["functions"]:
        if STOP.exists():
            log("fichier STOP trouve : arret.")
            break
        if name not in syms:
            continue
        addr, size, mode = syms[name]
        if mode != "arm" or any(a <= addr < b for a, b in covered):
            continue
        src = starting_draft(name)
        if not src:
            log(f"{name}: pas de brouillon (lancez l'auto-match ou la moulinette d'abord)")
            continue
        tried += 1
        work = WORK / f"{name}.c"
        work.write_text(src, encoding="utf-8", newline="\n")
        results = [(score(o), p, o) for p in profiles for _, o in [probe(work, name, addr, p)]]
        s0, profile, out0 = min(results, key=lambda r: r[0])
        log(f"{name} ({size} octets, {profile}) : depart {s0} instructions differentes")
        t0 = time.time()
        ok = s0 == 0 or chat_loop(work, name, addr, profile, out0)
        result = "pas de match"
        if ok:
            source = work.read_text(encoding="utf-8")
            if profile != profiles[0] and not source.startswith(am.MARKER):
                source = f"{am.MARKER}{profile} */\n" + source
            if integrate_and_verify(name, size, addr, source):
                run(["git", "add", "src/auto", f"config/{VERSION}"])
                run(["git", "commit", "-q", "-m", f"Match {name} (qwen, block {args.block})\n\nCo-Authored-By: Qwen <noreply@qwen.ai>\n",
                     "--", "src/auto", f"config/{VERSION}"])
                won += 1
                result = "MATCH + verifie + commite"
                if not args.no_push and run(["git", "remote"]).stdout.strip():
                    result += " + pousse" if run(["git", "push", "-q", "origin", "HEAD"]).returncode == 0 else " (push rate)"
            else:
                result = "match mais VERIFY echoue (annule)"
        touch_claim()
        log(f"{name}: {result} ({time.time() - t0:.0f}s)")
    log(f"fini : {won}/{tried} nouvelles fonctions sur le bloc {args.block}")


if __name__ == "__main__":
    main()
