"""Keeps the matching tools of every game up to date with the template (projets/rayman-rr/tools).

Each game has its own copy of the tools, adapted to it the same way tools/new_project.py does it (ROM name,
version folder, main .text range of auto_match). This module rebuilds that adapted copy from the template and
tells which games are behind.
"""
import hashlib
import re
import shutil
import time

from . import config, games, gitutil

TEMPLATE = config.PROJETS / "rayman-rr"
SYNC_TOOLS = ["auto_match.py", "probe_compiler.py", "pipeline_lock.py", "gen_context.py", "infer_signatures.py",
              "draft.py", "permute.py", "m2ctx.py"]


def _game_key(g) -> str:
    """'farm_frenzy' for projets/farm-frenzy (name used in <game>_<ver>.nds)."""
    for p in g.path.glob(f"*_{g.version}.sha1"):
        return p.name[:-len(f"_{g.version}.sha1")]
    return g.id.replace("-", "_")


def adapted(g, name: str) -> str | None:
    src = TEMPLATE / "tools" / name
    if not src.exists():
        return None
    t = src.read_text(encoding="utf-8")
    if g.id == TEMPLATE.name:
        return t
    key, ver = _game_key(g), g.version
    t = t.replace("rrr_usa", f"{key}_{ver}")
    t = re.sub(r'GAME = "rrr"', f'GAME = "{key}"', t)
    t = re.sub(r'(?<![\w.])usa(?![\w])', ver, t)
    t = t.replace("-lang=c\",              # The OpenSpace engine is written in C",
                  "-lang=c\",              # TODO: C++ games need -lang=c++")
    if name == "auto_match.py":  # keep the game's own main .text range
        cur = g.path / "tools" / name
        m = re.search(r"MAIN_TEXT = \(0x[0-9a-f]+, 0x[0-9a-f]+\)", cur.read_text(encoding="utf-8")) if cur.exists() else None
        if m is None:
            dl = (g.cfg / "delinks.txt").read_text(encoding="utf-8")
            r = re.search(r"\.text\s+start:0x([0-9a-f]+) end:0x([0-9a-f]+)", dl)
            m_text = f"MAIN_TEXT = (0x{r.group(1)}, 0x{r.group(2)})"
        else:
            m_text = m.group(0)
        t = re.sub(r"MAIN_TEXT = \(0x[0-9a-f]+, 0x[0-9a-f]+\)", m_text, t)
    return t


def _norm(s: str) -> str:
    return s.replace("\r\n", "\n")


def status(g) -> dict:
    """{'behind': [tool names whose content differs from the adapted template]}"""
    if not g.ready or g.id == TEMPLATE.name:
        return {"behind": []}
    behind = []
    for name in SYNC_TOOLS:
        want = adapted(g, name)
        cur = g.path / "tools" / name
        if want is None:
            continue
        if not cur.exists() or _norm(cur.read_text(encoding="utf-8", errors="replace")) != _norm(want):
            behind.append(name)
    return {"behind": behind}


def template_version() -> str:
    h = hashlib.sha1()
    for name in SYNC_TOOLS:
        p = TEMPLATE / "tools" / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:8]


def sync(g, commit=True, push=True, log=print) -> dict:
    """Writes the adapted template tools into the game. Old files are kept in build/tools_backup/<date>/."""
    if g.id == TEMPLATE.name:
        return {"ok": True, "changed": []}
    changed = status(g)["behind"]
    if not changed:
        return {"ok": True, "changed": []}
    backup = g.path / "build" / "tools_backup" / time.strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=True)
    for name in changed:
        cur = g.path / "tools" / name
        if cur.exists():
            shutil.copy2(cur, backup / name)
        cur.write_text(adapted(g, name), encoding="utf-8", newline="\n")
    log(f"{g.id}: {', '.join(changed)} mis a jour (anciens fichiers dans {backup.relative_to(g.path)})")
    if commit:
        paths = [f"tools/{n}" for n in changed]
        gitutil.git(g.path, "add", "--", *paths)
        r = gitutil.git(g.path, "commit", "-q", "-m", f"tools: sync {', '.join(changed)} from rayman-rr ({template_version()})",
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
