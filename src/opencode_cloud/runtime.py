"""Runtime detection and path management for ephemeral cloud runtimes.

Free of any Colab-specific dependencies.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RuntimePaths:
    """Paths inside an ephemeral runtime."""

    working: Path
    home: Path
    opencode_data: Path
    opencode_config: Path
    workspace: Path
    logs: Path
    temp: Path
    cloud_root: Path  # /kaggle/working/opencode_cloud


def detect_runtime() -> str:
    """Detect the current runtime platform.

    Returns:
        'kaggle' if running in Kaggle, otherwise 'local'.
    """
    if (
        os.path.exists("/kaggle")
        or os.environ.get("KAGGLE_KERNEL_EXECUTION")
        or os.environ.get("KAGGLE_CONTAINER_TYPE")
    ):
        return "kaggle"
    return "local"


def get_paths(runtime: Optional[str] = None) -> RuntimePaths:
    """Build RuntimePaths for the given runtime."""
    runtime = runtime or detect_runtime()
    home = Path.home()

    if runtime == "kaggle":
        working = Path("/kaggle/working")
    else:
        working = Path(os.environ.get("OPENCODE_CLOUD_WORKDIR", "/tmp/opencode-cloud"))

    cloud_root = working / "opencode_cloud"
    opencode_data = home / ".local" / "share" / "opencode"
    opencode_config = home / ".config" / "opencode"
    workspace = cloud_root / "workspace"
    logs = cloud_root / "logs"
    temp = cloud_root / "tmp"

    return RuntimePaths(
        working=working,
        home=home,
        opencode_data=opencode_data,
        opencode_config=opencode_config,
        workspace=workspace,
        logs=logs,
        temp=temp,
        cloud_root=cloud_root,
    )


def ensure_dirs(paths: RuntimePaths) -> None:
    """Create runtime directories idempotently."""
    for d in (
        paths.working,
        paths.cloud_root,
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
    return {
        "runtime": detect_runtime(),
        "platform": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
