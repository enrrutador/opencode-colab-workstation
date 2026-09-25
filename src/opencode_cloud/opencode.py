"""OpenCode bootstrap and management.

Idempotent:
- ensure_node(): if Node exists → skip; else install (or raise if not possible)
- ensure_opencode(): if OpenCode exists → skip; else install via npm

Config is merged incrementally; NVIDIA provider is preserved/updated without
wiping unrelated provider blocks when possible.
Secrets are never written into the config file — only env references.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def ensure_node() -> str:
    """Ensure Node.js is available. Idempotent. Returns version string."""
    result = subprocess.run(
        ["node", "--version"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()

    try:
        subprocess.run(
            ["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["apt-get", "install", "-y", "nodejs"],
            check=True,
            capture_output=True,
        )
    except Exception as e:
        raise RuntimeError(
            "Node.js is required but not installed and auto-install failed. "
            f"Install Node.js manually. Error: {e}"
        ) from e

    result = subprocess.run(
        ["node", "--version"], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("Node.js installation failed")
    return result.stdout.strip()


def ensure_opencode() -> str:
    """Ensure OpenCode CLI is installed. Idempotent. Returns binary path."""
    bin_path = shutil.which("opencode")
    if bin_path:
        return bin_path

    subprocess.run(
        ["npm", "install", "-g", "opencode-ai"],
        check=True,
        capture_output=True,
    )
    bin_path = shutil.which("opencode")
    if not bin_path:
        raise RuntimeError("OpenCode installation failed")
    return bin_path


def write_opencode_config(
    config_path: Path,
    model: Optional[str] = None,
    permission: str = "allow",
) -> Path:
    """Write or merge OpenCode configuration incrementally."""
    from .nvidia import build_opencode_config, build_provider_config

    new_cfg = build_opencode_config(model=model, permission=permission)
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if config_path.exists():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}

    if existing:
        merged = dict(existing)
        merged["$schema"] = new_cfg["$schema"]
        merged["permission"] = new_cfg["permission"]
        merged["compaction"] = new_cfg["compaction"]
        providers = dict(merged.get("provider") or {})
        nvidia_block = build_provider_config(model=model)["nvidia"]
        providers["nvidia"] = nvidia_block
        merged["provider"] = providers
        if model:
            merged["model"] = new_cfg["model"]
        final_cfg = merged
    else:
        final_cfg = new_cfg

    config_path.write_text(
        json.dumps(final_cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return config_path


def start_opencode_web(
    opencode_bin: str,
    workspace: Path,
    host: str = "0.0.0.0",
    port: int = 4096,
    env: Optional[dict] = None,
    log_path: Optional[Path] = None,
) -> subprocess.Popen:
    """Start OpenCode Web server. Returns Popen. Caller monitors it."""
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    if log_path is None:
        log_path = workspace.parent / "logs" / "opencode-web.log"
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [opencode_bin, "web", "--hostname", host, "--port", str(port)]
    log_handle = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    return proc
