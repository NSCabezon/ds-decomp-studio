#!/usr/bin/env python3
"""llama.cpp server for the Qwen agents: real parallel requests (continuous batching), even for models Ollama runs
one request at a time (qwen3.5).

    python workers/llm_server.py download                       # latest llama.cpp release for this PC (Vulkan)
    python workers/llm_server.py start --model qwen9-ctx --parallel 4 [--ctx 16384] [--url http://127.0.0.1:8080]
    python workers/llm_server.py status
    python workers/llm_server.py stop

No second copy of the model: `start` asks Ollama where its model file is (`ollama show --modelfile`, the FROM line:
a GGUF file llama.cpp reads as is). Each of the --parallel slots gets --ctx tokens of context.
Then run the agents with `qwen_block.py --backend openai` (the Studio setting "Serveur du modele").
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
TOOLS = STUDIO.parent / "tools" / "llama.cpp"  # decomp ds/tools/llama.cpp/<release>/llama-server.exe
STATE = STUDIO / "data" / "llm_server.json"
LOG = STUDIO / "data" / "logs" / "llm_server.log"
UA = {"User-Agent": "ds-decomp-studio"}


def server_exe() -> Path | None:
    env = os.environ.get("LLAMA_SERVER")
    if env and Path(env).exists():
        return Path(env)
    found = sorted(TOOLS.glob("*/llama-server.exe"), key=lambda p: p.stat().st_mtime) if TOOLS.exists() else []
    return found[-1] if found else (Path(shutil.which("llama-server")) if shutil.which("llama-server") else None)


def download(flavour: str) -> Path:
    """Unzips the latest llama.cpp Windows release (`bin-win-<flavour>-x64`) into tools/llama.cpp/<tag>/."""
    # the builds (bNNNNN) are published as prereleases; "latest" can be a release without binaries
    req = urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20", headers=UA)
    rel, asset = None, None
    for r in json.loads(urllib.request.urlopen(req, timeout=60).read()):
        asset = next((a for a in r["assets"] if re.search(rf"bin-win-{flavour}-x64\.zip$", a["name"])), None)
        if asset:
            rel = r
            break
    if asset is None:
        sys.exit(f"no llama-*-bin-win-{flavour}-x64.zip in the last 20 llama.cpp releases")
    dest = TOOLS / rel["tag_name"]
    if (dest / "llama-server.exe").exists():
        print(f"already there: {dest}")
        return dest
    print(f"downloading {asset['name']} ({asset['size'] // 2**20} MB)...", flush=True)
    data = urllib.request.urlopen(urllib.request.Request(asset["browser_download_url"], headers=UA), timeout=600).read()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for m in z.infolist():  # flat release zip; never write outside dest
            target = (dest / Path(m.filename).name)
            if not m.is_dir():
                target.write_bytes(z.read(m))
    print(f"llama.cpp {rel['tag_name']} -> {dest}")
    return dest


def ollama_model(model: str) -> tuple[Path, dict]:
    """(GGUF file, {parameter: value}) of an Ollama model."""
    exe = shutil.which("ollama") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    r = subprocess.run([exe, "show", "--modelfile", model], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode:
        sys.exit(f"ollama show {model}: {r.stderr.strip()}")
    gguf, params = None, {}
    for line in r.stdout.splitlines():
        m = re.match(r"FROM\s+(.+)$", line.strip())
        if m and Path(m.group(1).strip()).is_file() and gguf is None:
            gguf = Path(m.group(1).strip())
        m = re.match(r"PARAMETER\s+(\w+)\s+(.+)$", line.strip())
        if m:
            params[m.group(1)] = m.group(2).strip()
    if gguf is None:
        sys.exit(f"no model file found for {model} in `ollama show --modelfile`")
    return gguf, params


def main_gpu(exe: Path) -> str | None:
    """The dedicated GPU (`--list-devices`): without --device, llama.cpp also puts layers on an integrated GPU
    ("AMD Radeon(TM) Graphics", "Intel(R) UHD Graphics"), which is much slower."""
    r = subprocess.run([str(exe), "--list-devices"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=exe.parent)
    devs = re.findall(r"^\s*(\w+\d+):\s*(.+?)\s*\(", r.stdout + r.stderr, re.M)
    if len(devs) < 2:
        return None
    dedicated = [d for d, name in devs if not re.search(r"\(TM\) Graphics|UHD|Iris|Intel\(R\) Graphics", name + " (")]
    return (dedicated or [devs[0][0]])[0]


def running() -> dict | None:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        import psutil
        return st if psutil.pid_exists(st["pid"]) else None
    except ImportError:
        return st


def start(a) -> None:
    st = running()
    if st:
        print(f"already running (pid {st['pid']}, {st['model']}, {st['parallel']} slots, {st['url']})")
        return
    exe = server_exe()
    if exe is None:
        print("llama-server not found: downloading llama.cpp (Vulkan build, works on AMD and NVIDIA)...", flush=True)
        exe = download("vulkan") / "llama-server.exe"
    gguf, params = ollama_model(a.model)
    port = re.search(r":(\d+)", a.url.split("//", 1)[-1])
    port = port.group(1) if port else "8080"
    cmd = [str(exe), "-m", str(gguf), "--alias", a.model, "--host", "127.0.0.1", "--port", port,
           "-ngl", "999", "--parallel", str(a.parallel), "-c", str(a.ctx * a.parallel), "--jinja"]
    dev = a.device or main_gpu(exe)
    if dev:
        cmd += ["--device", dev]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = LOG.open("ab")
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # detached: outlives the job that started it
    env = dict(os.environ)
    if not a.coopmat:
        # Vulkan cooperative matrices give garbage with qwen3.5 on an RX 9070 XT (RDNA4), checked 2026-10-16:
        # correct text without them (90 tokens/s), so they stay off unless asked
        env.setdefault("GGML_VK_DISABLE_COOPMAT", "1")
        env.setdefault("GGML_VK_DISABLE_COOPMAT2", "1")
    p = subprocess.Popen(cmd, stdout=log, stderr=log, cwd=exe.parent, creationflags=flags, env=env)
    STATE.write_text(json.dumps({"pid": p.pid, "model": a.model, "parallel": a.parallel, "url": a.url,
                                 "cmd": cmd, "started": time.time()}), encoding="utf-8")
    print(f"llama-server pid {p.pid}: {a.model} ({gguf.name}), {a.parallel} slots x {a.ctx} tokens, {a.url}")
    print(f"log: {LOG}")


def stop() -> None:
    st = running()
    if not st:
        print("not running")
        return
    import psutil
    psutil.Process(st["pid"]).terminate()
    STATE.unlink(missing_ok=True)
    print(f"stopped pid {st['pid']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["download", "start", "stop", "status"])
    ap.add_argument("--model", default="qwen9-ctx", help="Ollama model name (its GGUF file is used)")
    ap.add_argument("--parallel", type=int, default=4, help="requests served at once (one slot each)")
    ap.add_argument("--ctx", type=int, default=16384, help="context tokens per slot")
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--device", help="llama.cpp device (default: the dedicated GPU, see --list-devices)")
    ap.add_argument("--coopmat", action="store_true", help="keep Vulkan cooperative matrices (wrong output on RDNA4)")
    ap.add_argument("--flavour", default="vulkan", help="download: release build (vulkan, cuda-12.4, hip-radeon...)")
    a = ap.parse_args()
    if a.action == "download":
        download(a.flavour)
    elif a.action == "start":
        start(a)
    elif a.action == "stop":
        stop()
    else:
        st = running()
        print(json.dumps(st, indent=1) if st else "not running")


if __name__ == "__main__":
    main()
