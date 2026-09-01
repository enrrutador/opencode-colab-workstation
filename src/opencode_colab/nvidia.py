import json
import subprocess

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

def fetch_models(api_key: str) -> list[str]:
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "30",
         "-H", f"Authorization: Bearer {api_key}",
         f"{NVIDIA_BASE_URL}/models"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
        return [item["id"] for item in payload.get("data", []) if item.get("id")]
    except Exception:
        return []

def select_model(available: list[str], preferred: str = "") -> str | None:
    if preferred and preferred in available:
        return preferred
    nemotron = [m for m in available if "nemotron" in m.lower()]
    if nemotron:
        return nemotron[0]
    return available[0] if available else None
