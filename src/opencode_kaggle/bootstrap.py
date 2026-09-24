"""Top-level bootstrap for OpenCode Cloud Workstation on Kaggle.

This is a minimal, notebook-friendly entry point. It detects the environment,
loads secrets, restores state, boots OpenCode, and starts the watchdog.

Use in a Kaggle notebook with:

```python
import opencode_kaggle.bootstrap as bs
bs.bootstrap()
```
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from opencode_cloud.checkpoint import CheckpointManager, CheckpointPolicy
from opencode_cloud.github_sync import configure_credential_helper, configure_remote, init_repo, sync_to_remote
from opencode_cloud.nvidia import fetch_models, select_model, build_opencode_config
from opencode_cloud.opencode import ensure_node, ensure_opencode, start_opencode_web, write_opencode_config
from opencode_cloud.persistence import default_store
from opencode_cloud.runtime import get_paths, ensure_dirs, is_kaggle
from opencode_cloud.secrets import load_required_secret, load_secret
from opencode_cloud.watchdog import Watchdog


def _log(msg: str) -> None:
    print(f"[OpenCode Cloud] {msg}")


def bootstrap(
    dataset_id: str | None = None,
    opencode_port: int = 4096,
    policy: CheckpointPolicy | None = None,
) -> dict:
    """Bootstrap the OpenCode Cloud Workstation on Kaggle.

    Returns a dict with runtime information for inspection.
    """
    if not is_kaggle():
        raise RuntimeError("This bootstrap is designed for Kaggle runtime.")

    paths = get_paths("kaggle")
    ensure_dirs(paths)

    _log(f"Working directory: {paths.working}")
    _log(f"Workspace: {paths.workspace}")

    # Secrets
    nvidia_key = load_required_secret("NVIDIA_API_KEY")
    github_repo = load_secret("GITHUB_REPO")
    github_token = load_secret("GITHUB_TOKEN")

    # Persistence store
    store = default_store(dataset_id)
    store.ensure_structure()

    # Restore state
    if store.has_files("state/opencode"):
        _log("Restoring OpenCode state...")
        store.sync_to("state/opencode", paths.opencode_data, delete=True)
    if store.has_files("state/config"):
        _log("Restoring OpenCode config...")
        store.sync_to("state/config", paths.opencode_config, delete=True)
    if store.has_files("workspace"):
        _log("Restoring workspace...")
        store.sync_to("workspace", paths.workspace, delete=True)

    # Bootstrap dependencies
    ensure_node()
    opencode_bin = ensure_opencode()

    # NVIDIA model selection
    models = fetch_models(nvidia_key)
    preferred = json.loads(store.read_json("state/runtime/metadata.json", {})) or {}
    preferred_model = preferred.get("nvidia_model", "")
    selected_model = select_model(models, preferred_model)
    if selected_model:
        _log(f"Selected model: {selected_model}")
        store.write_json("state/runtime/metadata.json", {"nvidia_model": selected_model})
    else:
        _log("No NVIDIA model selected. Continuing without model.")

    # Write OpenCode config
    cfg_path = paths.opencode_config / "opencode.json"
    write_opencode_config(cfg_path, model=selected_model)
    _log(f"OpenCode config written to {cfg_path}")

    # GitHub sync setup
    if github_repo:
        init_repo(paths.workspace)
        configure_remote(paths.workspace, github_repo)
        if github_token:
            cred_file = paths.working / "git_credentials"
            configure_credential_helper(paths.workspace, github_token, cred_file)

    # Start OpenCode
    env = os.environ.copy()
    env["NVIDIA_API_KEY"] = nvidia_key
    # Remove any auth variables that would block unauthenticated access
    for v in ["OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME", "OPENCODE_SERVER_AUTH"]:
        env.pop(v, None)

    proc = start_opencode_web(opencode_bin, paths.workspace, port=opencode_port, env=env)
    _log(f"OpenCode started, PID {proc.pid}")

    # Checkpoint manager
    ckpt_mgr = CheckpointManager(policy or CheckpointPolicy())

    # Persist initial state
    store.sync_from(paths.opencode_data, "state/opencode", delete=True)
    store.sync_from(paths.opencode_config, "state/config", delete=True)
    store.sync_from(paths.workspace, "workspace", delete=True)

    # Start watchdog
    def restart_action():
        _log("Restarting OpenCode process...")
        # Simple restart: start a new process
        new_proc = start_opencode_web(opencode_bin, paths.workspace, port=opencode_port, env=env)
        return new_proc

    def checkpoint_action():
        store.sync_from(paths.opencode_data, "state/opencode", delete=True)
        store.sync_from(paths.opencode_config, "state/config", delete=True)
        store.sync_from(paths.workspace, "workspace", delete=True)
        if github_repo:
            sync_to_remote(paths.workspace, "OpenCode automatic checkpoint")
        return True

    watchdog = Watchdog(check_interval=60, restart_callback=lambda: None, checkpoint_callback=checkpoint_action)
    watchdog.start()

    runtime_info = {
        "runtime": "kaggle",
        "workspace": str(paths.workspace),
        "opencode_port": opencode_port,
        "opencode_pid": proc.pid,
        "model": selected_model,
        "persistence": str(store.root if store.dataset_root else "not configured"),
    }

    return runtime_info