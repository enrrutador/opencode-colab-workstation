"""NVIDIA NIM provider configuration.

This module is responsible for:
- Detecting available NVIDIA NIM models.
- Selecting a default model.
- Building the OpenCode provider configuration.

It is intentionally independent of the persistence layer.
"""

from __future__ import annotations

import json
import subprocess
from typing import Optional

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def fetch_models(api_key: str) -> list[str]:
    """Fetch available NVIDIA NIM models.

    Args:
        api_key: NVIDIA API key.

    Returns:
        List of model IDs. Empty list on failure.
    """
    if not api_key:
        return []
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "30",
            "-H",
            f"Authorization: Bearer {api_key}",
            f"{NVIDIA_BASE_URL}/models",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
        return [item["id"] for item in payload.get("data", []) if item.get("id")]
    except Exception:
        return []


def select_model(available: list[str], preferred: str = "") -> Optional[str]:
    """Select a model from the available list.

    Preference order:
    1. Explicit preferred model (if available).
    2. First nemotron model.
    3. First available model.
    """
    if preferred and preferred in available:
        return preferred
    nemotron = [m for m in available if "nemotron" in m.lower()]
    if nemotron:
        return nemotron[0]
    return available[0] if available else None


def build_provider_config(api_key_env: str = "NVIDIA_API_KEY", model: Optional[str] = None) -> dict:
    """Build the NVIDIA provider section for OpenCode config."""
    cfg = {
        "name": "NVIDIA NIM",
        "npm": "@ai-sdk/openai-compatible",
        "options": {
            "baseURL": NVIDIA_BASE_URL,
            "apiKey": f"{{env:{api_key_env}}}",
        },
        "models": {},
    }
    if model:
        cfg["models"][model] = {"name": model}
    return {"nvidia": cfg}


def build_opencode_config(model: Optional[str] = None, permission: str = "allow") -> dict:
    """Build a complete OpenCode configuration dict."""
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "permission": permission,
        "compaction": {"auto": True, "prune": False},
        "provider": build_provider_config(model=model),
    }
    if model:
        cfg["model"] = f"nvidia/{model}"
    return cfg