"""Runtime detection and path management for ephemeral cloud runtimes.

This module provides a clean abstraction over the host runtime environment.
It is intentionally free of any Colab-specific dependencies.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RuntimePaths:
    """Paths inside an ephemeral runtime.

    Attributes:
        working: Runtime working directory (ephemeral, may disappear).
        home: User home directory inside the runtime.
        opencode_data: OpenCode state directory (~/.local/share/opencode).
        opencode_config: OpenCode config directory (~/.config/opencode).
        workspace: Local workspace directory (ephemeral).
        logs: Local logs directory (ephemeral).
        temp: Temporary files directory.
    """

    working: Path
    home: Path
    opencode_data: Path
    opencode_config: Path
    workspace: Path
    logs: Path
    temp: Path


def _env_path(name: str, default: Path) -> Path:
    val = os.environ.get(name)
    return Path(val) if val else default


def detect_runtime() -> str:
    """Detect the current runtime platform.

    Returns:
        'kaggle' if running in Kaggle, otherwise 'local'.
    """
    if os.path.exists("/kaggle") or os.environ.get("KAGGLE_KERNEL_EXECUTION") or os.environ.get("KAGGLE_CONTAINER_TYPE"):
        return "kaggle"
    return "local"


def get_paths(runtime: Optional[str] = None) -> RuntimePaths:
    """Build RuntimePaths for the given runtime.

    Args:
        runtime: Runtime identifier. Auto-detected when None.

    Returns:
        RuntimePaths instance.
    """
    runtime = runtime or detect_runtime()
    home = Path.home()

    if runtime == "kaggle":
        working = Path("/kaggle/working")
    else:
        working = Path(os.environ.get("OPENCODE_CLOUD_WORKDIR", "/tmp/opencode-cloud"))

    opencode_data = home / ".local" / "share" / "opencode"
    opencode_config = home / ".config" / "opencode"
    workspace = working / "opencode_workspace"
    logs = working / "opencode_logs"
    temp = working / "opencode_tmp"

    return RuntimePaths(
        working=working,
        home=home,
        opencode_data=opencode_data,
        opencode_config=opencode_config,
        workspace=workspace,
        logs=logs,
        temp=temp,
    )


def ensure_dirs(paths: RuntimePaths) -> None:
    """Create runtime directories idempotently."""
    for d in (
        paths.working,
        paths.workspace,
        paths.logs,
        paths.temp,
        paths.opencode_data,
        paths.opencode_config,
    ):
        Path(d).mkdir(parents=True, exist_ok=True)


def is_kaggle() -> bool:
    return detect_runtime() == "kaggle"


def is_local() -> bool:
    return detect_runtime() == "local"


def platform_info() -> dict:
    """Return a small dict of platform facts."""
    return {
        "runtime": detect_runtime(),
        "platform": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }