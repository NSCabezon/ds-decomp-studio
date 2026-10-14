"""Paths and settings of DS Decomp Studio.

The studio lives in `<workspace>/studio/`; the workspace is the DS toolbox folder that contains `projets/`, `roms/`,
`tools/`, `env.sh` and `fpdb.sqlite`. Override with the environment variable DSSTUDIO_ROOT.
"""
import json
import os
import shutil
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("DSSTUDIO_ROOT", STUDIO.parent)).resolve()
PROJETS = ROOT / "projets"
ARCHIVE = PROJETS / "_archive"
ANALYSE = PROJETS / "_analyse"
ROMS = ROOT / "roms"
TOOLS = ROOT / "tools"
FPDB = ROOT / "fpdb.sqlite"
ENV_SH = ROOT / "env.sh"
DATA = STUDIO / "data"  # local state, never committed
WEB = STUDIO / "web"
WORKERS = STUDIO / "workers"
PORT = int(os.environ.get("DSSTUDIO_PORT", "8765"))

DATA.mkdir(exist_ok=True)
SETTINGS_FILE = DATA / "settings.json"

# Folder of each game in the studio repo: everything the studio writes inside a game repo goes there
STUDIO_DIR = ".studio"
BLOCK_SIZE = 50
CLAIM_HOURS = 48  # a claimed block nobody touched for this long goes back to the queue


def _find_bash():
    for p in (ROOT.parent.parent / "Git" / "bin" / "bash.exe", Path("C:/Program Files/Git/bin/bash.exe"),
              Path("C:/Program Files (x86)/Git/bin/bash.exe")):
        if p.exists():
            return p
    w = shutil.which("bash")
    return Path(w) if w and "System32" not in w else None


BASH = _find_bash()

DEFAULTS = {
    "who": os.environ.get("USERNAME", "moi"),  # name used for claims
    "github_owner": "",                          # filled from `gh` on first publish
    "qwen_model": "qwen9-ctx",
    "qwen_minutes": 5,
    "qwen_agents": 4,                            # functions worked on at once (Ollama needs OLLAMA_NUM_PARALLEL >= this)
    "max_parallel_jobs": 2,
    "active_game": "",
    "push_claims": True,                         # claims are pushed to GitHub when the game has a remote
}


def settings() -> dict:
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    return {**DEFAULTS, **s}


def save_settings(changes: dict) -> dict:
    s = settings()
    s.update({k: v for k, v in changes.items() if k in DEFAULTS})
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    return s
