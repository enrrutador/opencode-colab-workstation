"""Kaggle-specific runtime adapter.

This module provides utilities to detect and interact with Kaggle kernel
environment without relying on Colab APIs.
"""

from __future__ import annotations

import os
from pathlib import Path


def is_kaggle_runtime() -> bool:
    """Return True if running inside a Kaggle kernel."""
    return (
        os.path.exists("/kaggle")
        or bool(os.environ.get("KAGGLE_KERNEL_EXECUTION"))
        or bool(os.environ.get("KAGGLE_CONTAINER_TYPE"))
    )


def get_runtime_paths() -> dict:
    """Return canonical Kaggle paths."""
    working = Path("/kaggle/working")
    input_root = Path("/kaggle/input")
    dataset_root = Path("/kaggle/datasets")

    return {
        "working": working,
        "input": input_root,
        "datasets": dataset_root,
        "home": Path.home(),
    }


def get_opencode_web_url(port: int = 4096) -> str:
    """Return a best-effort URL for accessing OpenCode Web from Kaggle.

    Kaggle does not provide a native proxy port like Colab. Public access to
    Kaggle kernel ports is limited. The recommended approach is to expose
    OpenCode Web via an external service or to use Kaggle's built-in
    notebook interface with tunnelling. This function documents the
    limitation.

    Returns:
        A documentation string explaining the limitation.
    """
    return (
        f"Kaggle kernels do not expose public URLs for services running on "
        f"port {port}. OpenCode Web is available locally at http://localhost:{port}. "
        "If you need remote access, use a supported tunnelling solution or "
        "access via the Kaggle UI."
    )