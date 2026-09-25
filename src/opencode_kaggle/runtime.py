"""Kaggle-specific runtime detection and documentation helpers."""

from __future__ import annotations

import os
from pathlib import Path


def is_kaggle_runtime() -> bool:
    return (
        os.path.exists("/kaggle")
        or bool(os.environ.get("KAGGLE_KERNEL_EXECUTION"))
        or bool(os.environ.get("KAGGLE_CONTAINER_TYPE"))
    )


def get_runtime_paths() -> dict:
    working = Path("/kaggle/working")
    return {
        "working": working,
        "input": Path("/kaggle/input"),
        "datasets_readonly_hint": Path("/kaggle/datasets"),
        "home": Path.home(),
        "cloud_root": working / "opencode_cloud",
    }


def describe_opencode_web_access(port: int = 4096) -> str:
    """Document access limitations. Does not invent public URLs or tunnels."""
    return (
        f"OpenCode Web is running locally inside the Kaggle runtime at "
        f"http://127.0.0.1:{port} (bound to 0.0.0.0:{port}). "
        "Kaggle does not provide an official public URL or proxy for arbitrary "
        "kernel ports. Access is local to the runtime; use the Kaggle notebook "
        "environment or an external tunnel you control if remote access is required."
    )
