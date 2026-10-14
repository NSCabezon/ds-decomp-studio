"""Small git helpers. Everything the studio commits lives in `.studio/` of the game repo, and is committed alone
(`git commit -- .studio`), so work in progress in src/ is never swept into a studio commit."""
import subprocess
from pathlib import Path

from . import config


def git(repo: Path, *args, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=0x08000000 if hasattr(subprocess, "STARTUPINFO") else 0)


def has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote").stdout.strip())


def pull(repo: Path) -> str:
    """Brings the remote state in (claims of the others). Returns an error message or ''."""
    if not has_remote(repo):
        return ""
    r = git(repo, "pull", "--rebase", "--autostash", "-q")
    if r.returncode != 0:
        git(repo, "rebase", "--abort")
        return (r.stderr or r.stdout).strip()[-400:]
    return ""


PRECOMMIT = ".pre-commit-config.yaml"
EXCLUDE_LINE = "exclude: ^\\.studio/  # queue data of DS Decomp Studio (clang-format would reformat the JSON)\n"


def ensure_ci_exclude(repo: Path) -> bool:
    """The game repos run clang-format in CI, and clang-format also formats .json files: keep .studio/ out of
    pre-commit. Returns True if the config file was changed."""
    p = repo / PRECOMMIT
    if not p.exists():
        return False
    text = p.read_text(encoding="utf-8")
    if "^\\.studio/" in text:
        return False
    p.write_text(EXCLUDE_LINE + text, encoding="utf-8", newline="\n")
    return True


def commit_studio(repo: Path, message: str) -> str:
    """Commits the .studio folder only (plus the pre-commit exclusion of .studio). Returns an error message or ''."""
    paths = [config.STUDIO_DIR]
    if ensure_ci_exclude(repo) or git(repo, "diff", "--name-only", "--", PRECOMMIT).stdout.strip():
        paths.append(PRECOMMIT)
    git(repo, "add", "-A", "--", *paths)
    if not git(repo, "diff", "--cached", "--name-only", "--", *paths).stdout.strip():
        return ""
    r = git(repo, "commit", "-q", "-m", message, "--", *paths)
    return "" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-400:]


def push(repo: Path) -> str:
    if not has_remote(repo) or not config.settings().get("push_claims", True):
        return ""
    for _ in range(3):
        r = git(repo, "push", "-q", "origin", "HEAD")
        if r.returncode == 0:
            return ""
        err = pull(repo)
        if err:
            return err
    return (r.stderr or r.stdout).strip()[-400:]
