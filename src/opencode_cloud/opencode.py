"""OpenCode bootstrap and management.

Idempotent bootstrap:
- Detects Node.js, npm, and OpenCode.
- Installs only what is missing.
- Does not re-install on subsequent runs.
- Configures OpenCode with the given provider configuration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def ensure_node() -> None:
    """Ensure Node.js is available. Installs Node 22 via Nodesource if missing."""
    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        return
    print("Node.js not found. Installing Node.js 22...")
    subprocess.run("curl -fsSL https://deb.nodesource.com/setup_22.x | bash -", shell=True, check=True)
    subprocess.run("apt-get install -y nodejs", shell=True, check=True)


def ensure_opencode() -> str:
    """Ensure OpenCode CLI is installed. Returns binary path."""
    bin_path = shutil.which("opencode")
    if bin_path:
        return bin_path
    print("Installing opencode-ai globally...")
    subprocess.run("npm install -g opencode-ai", shell=True, check=True)
    bin_path = shutil.which("opencode")
    if not bin_path:
        raise RuntimeError("OpenCode installation failed")
    return bin_path


def write_opencode_config(config_path: Path, model: Optional[str] = None, permission: str = "allow") -> Path:
    """Write or merge OpenCode configuration.

    Preserves existing provider configuration and only overwrites permission,
    compaction, and provider section as needed.
    """
    from .nvidia import build_opencode_config

    new_cfg = build_opencode_config(model=model, permission=permission)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        if isinstance(existing, dict):
            merged = dict(existing)
            merged["$schema"] = new_cfg["$schema"]
            merged["permission"] = new_cfg["permission"]
            merged["compaction"] = new_cfg["compaction"]
            merged["provider"] = new_cfg["provider"]
            if model:
                merged["model"] = new_cfg["model"]
            final_cfg = merged
        else:
            final_cfg = new_cfg
    else:
        final_cfg = new_cfg

    config_path.write_text(json.dumps(final_cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return config_path


def start_opencode_web(
    opencode_bin: str,
    workspace: Path,
    host: str = "0.0.0.0",
    port: int = 4096,
    env: Optional[dict] = None,
) -> subprocess.Popen:
    """Start OpenCode Web server.

    Returns the subprocess.Popen object. Caller is responsible for monitoring.
    """
    server_log = workspace.parent / "logs" / "opencode-web.log"
    server_log.parent.mkdir(parents=True, exist_ok=True)

    cmd = [opencode_bin, "web", "--hostname", host, "--port", str(port)]
    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        stdout=open(server_log, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    return proc