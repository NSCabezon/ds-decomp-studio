"""Machine tasks (build, verify, auto_match, moulinette, Qwen...) in a queue.

Rules: one task at a time per game (they all write in the project), at most `max_parallel_jobs` tasks at once.
Each task runs in Git Bash after `source env.sh`, its full log goes to data/logs/<n>.log.
"""
import json
import os
import re
import subprocess
import threading
import time

from . import config, games

LOGS = config.DATA / "logs"
LOGS.mkdir(exist_ok=True)
STATE = config.DATA / "jobs.json"
MOULINETTE = config.PROJETS / "rayman-rr" / "tools" / "moulinette.py"

# id: label, scope ("game" runs in the project, "global" in the workspace), expected seconds, description
DEFS = {
    "status": ("Statut de progression", "game", 20, "match.py status"),
    "build": ("Compiler (ninja)", "game", 120, "reconstruit la ROM"),
    "verify": ("Verifier (VERIFY PASSED)", "game", 90, "ROM identique + fichiers complets a 100 %"),
    "dis": ("Desassembler", "game", 60, "regenere build/<ver>/asm"),
    "auto": ("Auto-match", "game", 900, "m2c + compile + compare sur toutes les fonctions"),
    "permute": ("Auto-match + permuter", "game", 2400, "permuter sur les N near misses"),
    "moulinette": ("Moulinette complete", "game", 1800, "build, brouillons, auto-match, verify, commit (+push)"),
    "qwen": ("Qwen sur un bloc", "game", 3600, "IA locale (Ollama) sur les fonctions d'un bloc"),
    "scan": ("Indexer les empreintes (fingerprint)", "global", 180, "met a jour fpdb.sqlite"),
    "new_project": ("Ajouter un jeu", "global", 600, "dsd init + build depuis une ROM de roms/"),
    "publish": ("Publier sur GitHub", "game", 180, "cree le repo public et pousse"),
}

_lock = threading.RLock()
jobs: dict = {}
_seq = [0]
_procs: dict = {}


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


def command(jid: str, game, p: dict) -> str:
    v = game.version if game else ""
    if jid == "status":
        return "python tools/match.py status"
    if jid == "build":
        return "ninja"
    if jid == "verify":
        return "python tools/match.py verify"
    if jid == "dis":
        return f"rm -rf build/{v}/asm; ninja dis"
    if jid == "auto":
        return "python tools/auto_match.py"
    if jid == "permute":
        return f"python tools/auto_match.py --permute {int(p.get('n', 10))} --minutes {float(p.get('minutes', 2))}"
    if jid == "moulinette":
        extra = " --no-push" if not p.get("push") else ""
        return f"python {_q(MOULINETTE.as_posix())} --game {_q(game.id)}{extra}"
    if jid == "qwen":
        s = config.settings()
        return (f"python {_q((config.WORKERS / 'qwen_block.py').as_posix())} --project {_q(game.path.as_posix())}"
                f" --block {_q(p['block'])} --model {_q(p.get('model') or s['qwen_model'])}"
                f" --minutes {float(p.get('minutes') or s['qwen_minutes'])}")
    if jid == "scan":
        return "python tools/fingerprint.py scan projets/_analyse/*"
    if jid == "new_project":
        return f"python tools/new_project.py {_q(p['slug'])} {_q(p['rom'])}"
    if jid == "publish":
        return f"python {_q((config.STUDIO / 'studio.py').as_posix())} publish {_q(game.id)} --yes"
    raise KeyError(jid)


def _save():
    snap = [{k: v for k, v in j.items() if k != "log"} for j in jobs.values()]
    STATE.write_text(json.dumps(snap[-200:], ensure_ascii=False), encoding="utf-8")


def _restore():
    try:
        for j in json.loads(STATE.read_text(encoding="utf-8")):
            if j["state"] in ("running", "queued"):
                j["state"] = "interrupted"
            j["log"] = []
            jobs[j["n"]] = j
            _seq[0] = max(_seq[0], j["n"])
    except Exception:
        pass


def submit(jid: str, game_id: str | None, params: dict | None = None, who: str = "") -> dict:
    if jid not in DEFS:
        return {"error": f"tache inconnue : {jid}"}
    label, scope, expect, _ = DEFS[jid]
    params = params or {}
    game = None
    if scope == "game":
        try:
            game = games.get(game_id)
        except KeyError as e:
            return {"error": str(e)}
        if not game.ready and jid != "publish":
            return {"error": "projet incomplet : dsd init n'a pas abouti"}
        if jid in ("auto", "permute") and (game.path / ".auto_done").exists() and not params.get("force"):
            return {"error": "auto-match deja termine pour ce jeu (cocher 'forcer' pour relancer)"}
        if jid == "qwen" and not params.get("block"):
            return {"error": "choisir un bloc pour Qwen"}
    try:
        cmd = command(jid, game, params)
    except KeyError as e:
        return {"error": f"parametre manquant : {e}"}
    with _lock:
        _seq[0] += 1
        n = _seq[0]
        jobs[n] = {"n": n, "id": jid, "label": label, "game": game.id if game else None, "params": params,
                   "cmd": cmd, "who": who, "state": "queued", "queued": time.time(), "started": None, "ended": None,
                   "pct": 0, "expect": expect, "rc": None, "log": []}
        _save()
    _wake.set()
    return {"n": n}


def _start(j):
    game = games.get(j["game"]) if j["game"] else None
    cwd = game.path if game else config.ROOT
    env_line = f"source {_q(config.ENV_SH.as_posix())} >/dev/null 2>&1; " if config.ENV_SH.exists() else ""
    if config.FPDB.exists() and j["id"] == "qwen":
        env_line += f"export DSSTUDIO_ROOT={_q(config.ROOT.as_posix())}; "
    full = f"{env_line}cd {_q(cwd.as_posix())} && {j['cmd']}"
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    j["state"], j["started"] = "running", time.time()
    logf = (LOGS / f"{j['n']}.log").open("w", encoding="utf-8")
    logf.write(f"$ {j['cmd']}\n(dans {cwd})\n\n")
    try:
        p = subprocess.Popen([str(config.BASH), "-c", full], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env, creationflags=0x08000000)
    except Exception as e:
        j["state"], j["ended"] = "failed", time.time()
        j["log"].append(f"impossible de lancer Git Bash : {e}")
        logf.close()
        return
    _procs[j["n"]] = p

    def pump():
        for raw in iter(p.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            logf.write(line + "\n")
            logf.flush()
            j["log"].append(line)
            del j["log"][:-300]
            m = re.search(r"\[(\d+)/(\d+)\]", line)
            if m:
                j["pct"] = max(j["pct"], int(100 * int(m.group(1)) / max(int(m.group(2)), 1)))
        p.wait()
        logf.close()
        with _lock:
            j["rc"], j["ended"] = p.returncode, time.time()
            if j["state"] == "running":
                j["state"] = "done" if p.returncode == 0 else "failed"
            if j["state"] == "done":
                j["pct"] = 100
            if j["id"] == "verify" and j["state"] in ("done", "failed"):
                ok = any("VERIFY PASSED" in l for l in j["log"])
                games.set_health(j["game"], ok, "" if ok else (j["log"][-1] if j["log"] else "echec"))
            _procs.pop(j["n"], None)
            _save()
        _wake.set()
    threading.Thread(target=pump, daemon=True).start()


_wake = threading.Event()


def _scheduler():
    while True:
        _wake.wait(5)
        _wake.clear()
        with _lock:
            limit = int(config.settings().get("max_parallel_jobs", 2))
            running = [j for j in jobs.values() if j["state"] == "running"]
            busy = {j["game"] for j in running}
            for j in sorted((j for j in jobs.values() if j["state"] == "queued"), key=lambda j: j["n"]):
                if len(running) >= limit:
                    break
                if j["game"] in busy and j["game"] is not None:
                    continue
                if j["game"] is None and None in busy:  # global tasks also one at a time
                    continue
                _start(j)
                running.append(j)
                busy.add(j["game"])
            _save()


def start_scheduler():
    _restore()
    threading.Thread(target=_scheduler, daemon=True).start()


def cancel(n: int) -> bool:
    with _lock:
        j = jobs.get(n)
        if not j:
            return False
        if j["state"] == "queued":
            j["state"], j["ended"] = "cancelled", time.time()
            _save()
            return True
        p = _procs.get(n)
        if j["state"] == "running" and p:
            try:  # taskkill /T needs WMI, broken on some PCs: kill the tree with psutil
                import psutil
                parent = psutil.Process(p.pid)
                for c in parent.children(recursive=True):
                    c.kill()
                parent.kill()
            except Exception:
                p.kill()
            j["state"], j["ended"] = "stopped", time.time()
            _save()
            return True
    return False


def view(limit=40) -> list[dict]:
    out = []
    now = time.time()
    for n, j in sorted(jobs.items(), reverse=True)[:limit]:
        el = ((j["ended"] or now) - j["started"]) if j["started"] else 0
        pct = j["pct"]
        if j["state"] == "running" and pct == 0:
            pct = min(int(100 * el / max(j["expect"], 1)), 95)
        out.append({k: j[k] for k in ("n", "id", "label", "game", "state", "who", "params", "rc")} |
                   {"pct": pct, "elapsed": int(el), "queued_at": j["queued"], "log": j["log"][-80:]})
    return out


def full_log(n: int) -> str:
    p = LOGS / f"{int(n)}.log"
    return p.read_text(encoding="utf-8", errors="replace")[-200000:] if p.exists() else ""
