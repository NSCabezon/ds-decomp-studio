"""ByteMatch (https://bytematch.dev): public progress pages and badges of decompilation projects, fed by objdiff
reports.

The game repos cannot build their report in GitHub's CI (it needs the ROM), so the Studio uploads the report it
builds locally (build/<version>/report.json, made by `tools/match.py progress --rebuild`) through ByteMatch's upload
API, for the commit that is on GitHub. One upload token per project, created on its ByteMatch manage page, kept in
data/bytematch.json (data/ is never committed):

    python studio.py bytematch rayman-rr --token bm_...    # remember the token (once)
    python studio.py bytematch rayman-rr                   # upload now (the job `progress` does it too)
"""
import gzip
import json
import re
import urllib.parse
import urllib.request

from . import config, gitutil

SITE = "https://bytematch.dev"
TOKENS = config.DATA / "bytematch.json"
START, END = "<!-- bytematch:start -->", "<!-- bytematch:end -->"


def repo_of(g) -> str:
    """owner/repo of the game's GitHub remote ('' if none)."""
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", g.remote() or "")
    return m.group(1) if m else ""


def tokens() -> dict:
    try:
        return json.loads(TOKENS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def set_token(g, token: str) -> str:
    repo = repo_of(g)
    if not repo:
        raise SystemExit(f"{g.id} n'a pas de depot GitHub : publiez-le d'abord")
    if not token.startswith("bm_"):
        raise SystemExit("un jeton ByteMatch commence par bm_ (page Manage du projet sur bytematch.dev)")
    t = tokens()
    t[repo] = token
    TOKENS.write_text(json.dumps(t, indent=1), encoding="utf-8")
    return repo


def version_of(g) -> str:
    """The version name shown on ByteMatch: the game code of the ROM (AR5E), else the config folder (usa)."""
    return g.code or g.version


def badges(g) -> str:
    repo = repo_of(g)
    page = f"{SITE}/{repo}"
    items = [("Code", "matched_code_percent"), ("Data", "matched_data_percent"), ("Functions", "matched_functions")]
    line = " ".join(f"[![{label}]({page}.svg?label={label}&measure={m})]({page})" for label, m in items)
    return f"{START}\n{line}\n{END}"


def add_badges(g) -> bool:
    """Badges under the README title (once). True if the README changed."""
    p = g.path / "README.md"
    text = p.read_text(encoding="utf-8")
    block = badges(g)
    # the block is always rewritten under the title: `# Title`, or a title underlined with ===== (Rayman's README)
    rest = re.sub(r"\n*" + re.escape(START) + r".*?" + re.escape(END) + r"\n*", "\n\n", text, flags=re.S)
    rest = rest.lstrip("\n")
    m = re.search(r"^# .*\n", rest, re.M) or re.search(r"^=+[ \t]*\n", rest, re.M)
    at = m.end() if m else 0
    new = rest[:at] + "\n" + block + "\n\n" + rest[at:].lstrip("\n")
    if new != text:
        p.write_text(new, encoding="utf-8", newline="\n")
    return new != text


def upload(g, log=print) -> bool:
    """Sends build/<version>/report.json for the commit HEAD (already pushed). False if not set up or refused."""
    repo = repo_of(g)
    token = tokens().get(repo)
    if not token:
        return False
    report = g.path / "build" / g.version / "report.json"
    if not report.exists():
        log("  ByteMatch : pas de report.json (lancer match.py progress --rebuild)")
        return False
    sha = gitutil.git(g.path, "rev-parse", "HEAD").stdout.strip()
    msg = gitutil.git(g.path, "log", "-1", "--format=%s").stdout.strip()
    when = gitutil.git(g.path, "log", "-1", "--format=%cI").stdout.strip()
    query = urllib.parse.urlencode({"version": version_of(g), "commit": sha, "commit_message": msg,
                                    "commit_timestamp": when})
    req = urllib.request.Request(f"{SITE}/api/v1/projects/{repo}/reports?{query}",
                                 data=gzip.compress(report.read_bytes()), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Encoding": "gzip",
                                          "Content-Type": "application/json",
                                          # Cloudflare refuses Python's default agent (error 1010)
                                          "User-Agent": "ds-decomp-studio (+https://github.com/liolu/ds-decomp-studio)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            answer = json.loads(r.read() or b"{}")
        log(f"  ByteMatch : rapport {version_of(g)} envoye ({answer.get('url', SITE + '/' + repo)})")
        return True
    except urllib.error.HTTPError as e:
        log(f"  ByteMatch : refuse ({e.code}) {e.read()[:300].decode('utf-8', 'replace')}")
    except Exception as e:
        log(f"  ByteMatch : envoi impossible ({e})")
    return False
