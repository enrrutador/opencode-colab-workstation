import json
import shutil
import subprocess
from pathlib import Path

def ensure_node():
    r = subprocess.run("node --version", shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(
            "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs",
            shell=True, check=True
        )

def ensure_opencode():
    if shutil.which("opencode") is None:
        subprocess.run("npm install -g opencode-ai", shell=True, check=True)
    return shutil.which("opencode")

def write_config(config_path: Path, nvidia_api_key_env: str = "NVIDIA_API_KEY", model: str | None = None):
    """Genera ~/.config/opencode/opencode.json. Fuerza permission=allow y provider nvidia."""
    from src.opencode_colab.nvidia import NVIDIA_BASE_URL
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "permission": "allow",
        "compaction": {"auto": True, "prune": False},
        "provider": {
            "nvidia": {
                "name": "NVIDIA NIM",
                "npm": "@ai-sdk/openai-compatible",
                "options": {"baseURL": NVIDIA_BASE_URL, "apiKey": "{env:NVIDIA_API_KEY}"},
                "models": {}
            }
        }
    }
    if model:
        cfg["provider"]["nvidia"]["models"][model] = {"name": model}
        cfg["model"] = f"nvidia/{model}"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg
