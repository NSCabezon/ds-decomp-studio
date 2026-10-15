"""Publishes the progress: the "Progress" section of every published game's README (tools/match.py progress), then
the table of every game in the Studio's README (readme.py), each committed and pushed. Games registered on
ByteMatch (an upload token in data/bytematch.json, see bytematch.py) also get its badges and their report uploaded.

    python studio.py progress                 # every game that has a GitHub repo, then the Studio
    python studio.py progress --game rayman-rr --no-push

A game busy with another tool (build/pipeline.lock held by a running process) is skipped: its report would be
read while it changes.
"""
import json
import re
import subprocess
import sys

from . import bytematch, config, games, gitutil, readme

MSG = "README: progress section (tools/match.py progress)\n\nUpdated by DS Decomp Studio (job progress)."


def busy(g) -> str:
    lock = g.path / "build" / "pipeline.lock"
    if not lock.exists():
        return ""
    try:
        info = json.loads(lock.read_text())
        import psutil
        if psutil.pid_exists(int(info.get("pid", 0))):
            return info.get("owner", "another tool")
    except Exception:
        pass
    return ""


def fix_title(g) -> None:
    """The README title of the template is the folder name: use the game's real title."""
    p = g.path / "README.md"
    t = p.read_text(encoding="utf-8")
    n = re.sub(r"^# .*? decompilation \(", f"# {g.title} decompilation (", t, count=1, flags=re.M)
    if n != t:
        p.write_text(n, encoding="utf-8", newline="\n")


def commit_push(repo, paths, message, push=True, log=print) -> None:
    if not gitutil.git(repo, "status", "--porcelain", "--", *paths).stdout.strip():
        log("  inchange")
        return
    r = gitutil.git(repo, "commit", "-q", "-m", message, "--", *paths)
    if r.returncode:
        log("  commit impossible : " + (r.stderr or r.stdout).strip()[-300:])
        return
    if push and gitutil.has_remote(repo):
        r = gitutil.git(repo, "push", "-q", "origin", "HEAD", timeout=300)
        log("  pousse" if r.returncode == 0 else "  push rate : " + r.stderr.strip()[-300:])
    else:
        log("  commite (pas de push)")


def run(game_id: str = "", push: bool = True, log=print) -> None:
    todo = [games.get(game_id)] if game_id else [g for g in games.all_games() if g.ready and g.remote()]
    for i, g in enumerate(todo, 1):
        log(f"[{i}/{len(todo) + 1}] {g.id}")
        who = busy(g)
        if who:
            log(f"  saute : {who} travaille sur ce jeu")
            continue
        # the README needs no build (match.py reads the configuration); ByteMatch needs objdiff's report
        rebuild = ["--rebuild"] if bytematch.repo_of(g) in bytematch.tokens() else []
        if rebuild:
            subprocess.run([sys.executable, "tools/configure.py", g.version], cwd=g.path, capture_output=True)
        r = subprocess.run([sys.executable, "tools/match.py", "progress", *rebuild], cwd=g.path,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode:
            log("  echec : " + (r.stdout + r.stderr).strip().splitlines()[-1][:300] if (r.stdout + r.stderr).strip()
                else "  echec")
            continue
        log("  " + r.stdout.strip().splitlines()[-1])
        fix_title(g)
        if bytematch.repo_of(g) in bytematch.tokens():
            bytematch.add_badges(g)
        commit_push(g.path, ["README.md"], MSG + "\n", push, log)
        if push:
            bytematch.upload(g, log)  # for the commit now on GitHub; nothing without a token
    log(f"[{len(todo) + 1}/{len(todo) + 1}] DS Decomp Studio")
    readme.update()
    commit_push(config.STUDIO, ["README.md"], "README: progress of every game (job progress)\n", push, log)
