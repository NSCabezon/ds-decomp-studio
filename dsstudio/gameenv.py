"""The environment of `env.sh`, for tools the studio starts without Git Bash (the MCP server, the C editor): the
toolbox's tools, compilers, m2c, the ARM toolchain and the venv on PATH."""
import os
import subprocess
import sys
from pathlib import Path

from . import config

ARM_BIN = Path("C:/Program Files (x86)/Arm GNU Toolchain arm-none-eabi/14.2 rel1/bin")
VENV = config.ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
_VENV_PYTHON = VENV / ("python.exe" if os.name == "nt" else "python")
PYTHON = _VENV_PYTHON if _VENV_PYTHON.exists() else Path(sys.executable)


def env() -> dict:
    e = dict(os.environ)
    tools = config.TOOLS
    extra = [tools, tools / "melonDS", tools / "ghidra_11.2.1_PUBLIC", ARM_BIN, VENV]
    winlibs = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for p in winlibs.glob("BrechtSanders.WinLibs*/mingw64/bin") if winlibs.is_dir() else []:
        extra.append(p)
    e["PATH"] = os.pathsep.join(str(p) for p in extra[:5]) + os.pathsep + e.get("PATH", "") + \
        "".join(os.pathsep + str(p) for p in extra[5:])
    # Toolbox copies when the toolbox has them; otherwise each game falls back to its own tools/ (configure.py
    # downloads tools/mwccarm)
    for var, sub in (("MWCCARM", "mwccarm"), ("M2C_PATH", "m2c"), ("PERMUTER_PATH", "decomp-permuter")):
        if (tools / sub).is_dir():
            e[var] = str(tools / sub)
    if VENV.is_dir():
        e["VIRTUAL_ENV"] = str(VENV.parent)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def workbench(game_path: Path, *args: str, timeout: float = 3600) -> dict:
    """Runs tools/workbench.py in a game and returns its JSON answer."""
    import json
    if not (game_path / "tools" / "workbench.py").exists():
        return {"error": "this game's tools are behind: run the job 'Mettre a jour les outils' (sync-tools)"}
    r = subprocess.run([str(PYTHON), "tools/workbench.py", *args], cwd=game_path, env=env(), capture_output=True, stdin=subprocess.DEVNULL,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    for line in reversed((r.stdout or "").strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {"error": "workbench failed", "output": ((r.stdout or "") + (r.stderr or ""))[-3000:]}
