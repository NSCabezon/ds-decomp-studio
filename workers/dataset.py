#!/usr/bin/env python3
"""Training data for a model specialized in mwccarm: every matched function of our games as (assembly -> the C that
compiles to it exactly), in the chat format of LoRA fine-tuning tools (unsloth, axolotl, LLaMA-Factory, mlx-lm).

    python workers/dataset.py                 # -> decomp ds/datasets/mwcc_asm2c_{train,val}.jsonl
    python workers/dataset.py --val 0.05 --max-size 400

Source: decomp ds/examples.sqlite (workers/examples.py build). One line per function, the same code only once
(several games share the SDK), assembly-language functions excluded. The validation part is chosen by a hash of the
assembly, so it stays the same between exports.

Training (not done here): a 7B coder model with QLoRA needs a GPU that the training tools support: NVIDIA (CUDA),
or AMD with ROCm on Linux (unsloth and bitsandbytes do not run on AMD under Windows). A rented GPU or a Linux/WSL
setup works; the result is a GGUF that Ollama / llama.cpp load like the current model.
"""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
DB = WORKSPACE / "examples.sqlite"
OUT = WORKSPACE / "datasets"
SYSTEM = ("You write C for a matching decompilation of a Nintendo DS game: the C must compile with Metrowerks "
          "mwccarm (ARM, -O4,p unless told otherwise) to exactly the given assembly.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--val", type=float, default=0.05, help="part kept for validation")
    ap.add_argument("--max-size", type=int, default=512, help="largest function in bytes")
    a = ap.parse_args()
    if not DB.exists():
        raise SystemExit(f"{DB} missing: run `python workers/examples.py build` first")
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT game, name, size, asm, c, profile FROM ex WHERE size <= ?", (a.max_size,)).fetchall()
    OUT.mkdir(exist_ok=True)
    seen, n = set(), {"train": 0, "val": 0}
    files = {k: (OUT / f"mwcc_asm2c_{k}.jsonl").open("w", encoding="utf-8", newline="\n") for k in n}
    for game, name, size, asm, c, profile in rows:
        key = hashlib.sha1(re.sub(r"0x[0-9a-f]{6,}", "X", asm).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        compiler = (profile or "2.0/sp1p5").split(" ")
        user = (f"Compiler: mwccarm {compiler[0]}{' ' + ' '.join(compiler[1:]) if len(compiler) > 1 else ''}\n"
                f"Function {name} ({size} bytes):\n```\n{asm}\n```")
        rec = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user},
                            {"role": "assistant", "content": f"```c\n{c.strip()}\n```"}],
               "meta": {"game": game, "function": name}}
        part = "val" if int(key[:8], 16) / 0xFFFFFFFF < a.val else "train"
        files[part].write(json.dumps(rec, ensure_ascii=True) + "\n")
        n[part] += 1
    for f in files.values():
        f.close()
    print(f"{n['train']} train + {n['val']} validation examples -> {OUT} ({len(rows) - len(seen)} duplicates left out)")


if __name__ == "__main__":
    main()
