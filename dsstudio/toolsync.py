"""One version of the matching tools for every game.

The single source is `studio/gametools/`. The tools read everything game-specific (version, ROM name, main .text
range) from the project through `tools/project.py`, so they are byte-identical in every game: syncing is a plain
copy. Each game keeps a copy in its repo, so a clone of one game works on its own (and its CI sees the tools).
`tools/configure.py` stays per game (compiler and flags of that game) and is never touched.
"""
import hashlib
import shutil
import time

from . import config, games, gitutil

SOURCE = config.STUDIO / "gametools"


def tool_names() -> list[str]:
    return sorted(p.name for p in SOURCE.glob("*.py"))


def adapted(g, name: str) -> str | None:
    """Content the game should have (kept for the callers of the previous, per-game version)."""
    p = SOURCE / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def status(g) -> dict:
    """{'behind': [tools whose content differs from gametools/]}"""
    if not g.ready:
        return {"behind": []}
    behind = []
    for name in tool_names():
        cur = g.path / "tools" / name
        if not cur.exists() or _norm(cur.read_bytes()) != _norm((SOURCE / name).read_bytes()):
            behind.append(name)
    return {"behind": behind}


def template_version() -> str:
    h = hashlib.sha1()
    for name in tool_names():
        h.update(_norm((SOURCE / name).read_bytes()))
    return h.hexdigest()[:8]


def sync(g, commit=True, push=True, log=print) -> dict:
    """Copies gametools/ into the game. Replaced files are kept in build/tools_backup/<date>/."""
    changed = status(g)["behind"]
    if not changed:
        return {"ok": True, "changed": []}
    backup = g.path / "build" / "tools_backup" / time.strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=True)
    for name in changed:
        cur = g.path / "tools" / name
        if cur.exists():
            shutil.copy2(cur, backup / name)
        cur.write_bytes(_norm((SOURCE / name).read_bytes()))
    log(f"{g.id}: {', '.join(changed)} mis a jour (anciens fichiers dans {backup.relative_to(g.path)})")
    if commit:
        paths = [f"tools/{n}" for n in changed]
        gitutil.git(g.path, "add", "--", *paths)
        r = gitutil.git(g.path, "commit", "-q", "-m",
                        f"tools: sync {', '.join(changed)} from ds-decomp-studio/gametools ({template_version()})",
                        "--", *paths)
        if r.returncode:
            return {"error": r.stderr.strip()[-300:], "changed": changed}
        if push and g.remote():
            err = gitutil.push(g.path)
            if err:
                return {"ok": True, "changed": changed, "warning": f"push : {err}"}
    return {"ok": True, "changed": changed}


def sync_all(log=print) -> list:
    return [{"game": g.id, **sync(g, log=log)} for g in games.all_games() if g.ready]
