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
    """Legacy string description. Prefer AccessLayer / bootstrap web_access dict."""
    return (
        f"OpenCode listens on 127.0.0.1:{port} inside the Kaggle runtime. "
        "Kaggle does not publish this port. bootstrap() starts a Cloudflare Tunnel "
        "(cloudflared) and returns web_access.url when available. "
        "Protect OpenCode with the OPENCODE_SERVER_PASSWORD Kaggle Secret."
    )
