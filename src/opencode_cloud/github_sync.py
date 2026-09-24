"""GitHub synchronization for OpenCode Cloud Workstation.

Security-first design:
- Uses subprocess with list arguments (no shell=True) wherever possible.
- Never interpolates tokens into command strings.
- Uses git credential helpers with file-based storage, chmod 600.
- Validates repository URLs to prevent injection.
- Never logs tokens.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+\.git$")


def validate_repo_url(url: str) -> str:
    """Validate and normalize a GitHub HTTPS URL."""
    if not url:
        return ""
    url = url.strip().rstrip("/")
    if not url.endswith(".git"):
        url += ".git"
    if not _URL_RE.match(url):
        raise ValueError(f"Invalid or unsupported GitHub repository URL: {url!r}")
    return url


def _run(args: list[str], cwd: Optional[Path] = None, env: Optional[dict] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a git command safely without shell=True."""
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=capture,
        text=True,
    )


def init_repo(workspace: Path) -> None:
    """Initialize a git repository in workspace if not already present."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    if not (workspace / ".git").exists():
        _run(["git", "init"], cwd=workspace, capture=False)
        _run(["git", "checkout", "-B", "main"], cwd=workspace, capture=False)
    _run(["git", "config", "user.name", "OpenCode Cloud Workstation"], cwd=workspace, capture=False)
    _run(["git", "config", "user.email", "opencode-cloud@localhost"], cwd=workspace, capture=False)


def configure_remote(workspace: Path, repo_url: str) -> None:
    """Configure the origin remote safely."""
    repo_url = validate_repo_url(repo_url)
    workspace = Path(workspace)
    _run(["git", "remote", "remove", "origin"], cwd=workspace, capture=True)
    _run(["git", "remote", "add", "origin", repo_url], cwd=workspace, capture=True)


def configure_credential_helper(workspace: Path, token: str, credential_file: Path) -> None:
    """Configure git credential helper with a token stored in a secure file.

    The token is written to a file with chmod 600 and never appears in
    command arguments or logs.
    """
    credential_file = Path(credential_file)
    credential_file.parent.mkdir(parents=True, exist_ok=True)
    # Write the credential in the format expected by git credential store.
    credential_file.write_text(f"https://x-access-token:{token}@github.com\n", encoding="utf-8")
    try:
        os.chmod(credential_file, 0o600)
    except Exception:
        pass
    _run(
        ["git", "config", "credential.helper", f"store --file={credential_file}"],
        cwd=str(workspace),
        capture=True,
    )


def fetch_origin(workspace: Path, env: Optional[dict] = None) -> bool:
    """Fetch from origin. Returns True on success."""
    result = _run(["git", "fetch", "origin"], cwd=str(workspace), env=env)
    return result.returncode == 0


def merge_origin_main(workspace: Path, env: Optional[dict] = None) -> bool:
    """Merge origin/main into current branch. Returns True on success."""
    result = _run(["git", "merge", "origin/main", "--no-edit"], cwd=str(workspace), env=env)
    return result.returncode == 0


def add_all(workspace: Path) -> None:
    _run(["git", "add", "-A"], cwd=str(workspace), capture=True)


def status_porcelain(workspace: Path) -> str:
    result = _run(["git", "status", "--porcelain"], cwd=str(workspace))
    return result.stdout


def commit(workspace: Path, message: str) -> bool:
    result = _run(["git", "commit", "-m", message], cwd=str(workspace))
    return result.returncode == 0


def push_origin_main(workspace: Path, env: Optional[dict] = None) -> bool:
    result = _run(["git", "push", "-u", "origin", "main"], cwd=str(workspace), env=env)
    return result.returncode == 0


def sync_to_remote(workspace: Path, message: str, env: Optional[dict] = None) -> bool:
    """Add, commit, and push. Returns True if push succeeded."""
    add_all(workspace)
    status = status_porcelain(workspace)
    if status.strip():
        commit(workspace, message)
    return push_origin_main(workspace, env=env)


def restore_from_remote(workspace: Path, env: Optional[dict] = None) -> bool:
    """Clone or fetch+merge from origin. Returns True on success."""
    workspace = Path(workspace)
    if not (workspace / ".git").exists():
        # Fresh clone into empty directory
        if workspace.exists() and any(workspace.iterdir()):
            raise RuntimeError("Cannot clone into non-empty directory without .git")
        workspace.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "origin", str(workspace)],
            cwd=str(workspace.parent),
            env=env,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    else:
        if not fetch_origin(workspace, env=env):
            return False
        return merge_origin_main(workspace, env=env)