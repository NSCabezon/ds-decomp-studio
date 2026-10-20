import argparse
from pathlib import Path
from get_platform import get_platform
import zipfile
import io
import os
import stat

root_path = Path(__file__).parent.parent


platform = get_platform()
if platform is None:
    exit(1)

parser = argparse.ArgumentParser()
parser.add_argument("tool")
parser.add_argument("tag")
parser.add_argument("--path", type=Path, required=True)
args = parser.parse_args()


def dsd_url(tag: str) -> str:
    return f'https://github.com/AetiasHax/ds-decomp/releases/download/{tag}/dsd-{platform.system}-{platform.machine}{platform.exe}'

def mwccarm_url(tag: str) -> str:
    return 'http://decomp.aetias.com/files/mwccarm.zip'

def wibo_url(tag: str) -> str:
    # macOS: one x86_64 Mach-O build (wibo >= 1.0), runs under Rosetta 2 on Apple Silicon
    asset = 'wibo-macos' if platform.system == 'macos' else 'wibo'
    return f'https://github.com/decompals/wibo/releases/download/{tag}/{asset}'

def objdiff_url(tag: str) -> str:
    return f'https://github.com/encounter/objdiff/releases/download/{tag}/objdiff-cli-{platform.system}-{platform.machine}{platform.exe}'

def sjiswrap_url(tag: str) -> str:
    return f'https://github.com/encounter/sjiswrap/releases/download/{tag}/sjiswrap-windows-x86.exe'

TOOLS = {
    "dsd": dsd_url,
    "mwccarm": mwccarm_url,
    "wibo": wibo_url,
    "objdiff": objdiff_url,
    "sjiswrap": sjiswrap_url,
}


def fetch(url: str) -> bytes:
    try:
        import requests
    except ImportError:  # plain python3 (e.g. macOS without a venv): the standard library is enough
        import urllib.request
        with urllib.request.urlopen(url) as r:
            return r.read()
    response = requests.get(url)
    response.raise_for_status()
    return response.content


download_url = TOOLS[args.tool](args.tag)
print(f'\nDownloading {args.tool} {args.tag}...')
content = fetch(download_url)
if download_url.endswith('.zip'):
    zip_file = zipfile.ZipFile(io.BytesIO(content))
    zip_file.extractall(args.path)
else:
    out_path: Path = args.path
    # Write a new file and rename it over the old one: on macOS, rewriting an executable that already ran in place
    # makes the kernel kill it (SIGKILL, cached code signature of the old file)
    tmp_path = out_path.with_name(out_path.name + '.download')
    with tmp_path.open('wb') as f:
        f.write(content)
    tmp_path.chmod(tmp_path.stat().st_mode | stat.S_IEXEC)
    os.replace(tmp_path, out_path)
