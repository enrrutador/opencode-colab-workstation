"""Top-level bootstrap for OpenCode Cloud Workstation on Kaggle.

Flow:
  1. Detect Kaggle
  2. Init local dirs (/kaggle/working/opencode_cloud)
  3. Load Kaggle Secrets
  4. Identify Dataset
  5. Download + recover (or FRESH)
  6. Restore runtime paths
  7. Ensure Node + OpenCode (idempotent)
  8. Configure NVIDIA NIM (env-only secrets)
  9. Start OpenCode Web locally
 10. Start Watchdog with REAL restart
 11. Local checkpoints; remote via CheckpointManager policy

GitHub is optional code versioning with temporary credentials only.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from typing import Optional

from opencode_cloud.checkpoint import CheckpointManager, CheckpointPolicy, PublishReason
from opencode_cloud.github_sync import (
    configure_remote,
    init_repo,
    sync_to_remote,
)
from opencode_cloud.nvidia import fetch_models, select_model
from opencode_cloud.opencode import (
    ensure_node,
    ensure_opencode,
    start_opencode_web,
    write_opencode_config,
)
from opencode_cloud.persistence import (
    KagglePersistence,
    PersistentStore,
    RecoveryStatus,
    default_store,
)
from opencode_cloud.runtime import ensure_dirs, get_paths, is_kaggle
from opencode_cloud.secrets import load_required_secret, load_secret
from opencode_cloud.watchdog import Watchdog
from opencode_kaggle.kaggle import resolve_dataset_id
from opencode_kaggle.runtime import describe_opencode_web_access


def _log(msg: str) -> None:
    print(f"[OpenCode Cloud] {msg}")


def bootstrap(
    dataset_id: Optional[str] = None,
    opencode_port: int = 4096,
    policy: Optional[CheckpointPolicy] = None,
) -> dict:
    """Bootstrap the workstation. Returns runtime info dict."""
    if not is_kaggle():
        # Allow local dry-run when OPENCODE_CLOUD_ALLOW_LOCAL=1
        if os.environ.get("OPENCODE_CLOUD_ALLOW_LOCAL") != "1":
            raise RuntimeError(
                "This bootstrap targets Kaggle. "
                "Set OPENCODE_CLOUD_ALLOW_LOCAL=1 for local testing."
            )

    paths = get_paths()
    ensure_dirs(paths)
    store = default_store(paths.working)

    _log(f"Working: {paths.working}")
    _log(f"Cloud root: {paths.cloud_root}")

    # --- Secrets (Kaggle Secrets / env) ---
    nvidia_key = load_required_secret("NVIDIA_API_KEY")
    github_repo = load_secret("GITHUB_REPO")
    github_token = load_secret("GITHUB_TOKEN")
    # Dataset id is configuration, not necessarily a secret
    try:
        did = resolve_dataset_id(dataset_id)
    except Exception as e:
        raise RuntimeError(f"Dataset configuration error: {e}") from e

    persistence = KagglePersistence(did, paths.working)

    # --- Recovery ---
    recovery = persistence.recover_into(store)
    _log(f"Recovery: {recovery.status.value} — {recovery.message}")

    if recovery.status == RecoveryStatus.RESTORE_FAILED:
        # Do not pretend success
        return {
            "runtime": "kaggle",
            "recovery": recovery.status.value,
            "message": recovery.message,
            "ok": False,
        }

    # Restore into OpenCode runtime paths
    store.restore_to(
        opencode_data=paths.opencode_data,
        opencode_config=paths.opencode_config,
        workspace=paths.workspace,
    )

    # --- Tooling (idempotent) ---
    node_ver = ensure_node()
    _log(f"Node: {node_ver}")
    opencode_bin = ensure_opencode()
    _log(f"OpenCode: {opencode_bin}")

    # --- NVIDIA ---
    models = fetch_models(nvidia_key)
    preferred = ""
    meta_path = store.metadata_dir / "nvidia.json"
    if meta_path.exists():
        try:
            preferred = json.loads(meta_path.read_text(encoding="utf-8")).get(
                "model", ""
            )
        except Exception:
            preferred = ""
    selected_model = select_model(models, preferred)
    if selected_model:
        _log(f"Model: {selected_model}")
        store.metadata_dir.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps({"model": selected_model}, indent=2), encoding="utf-8"
        )
    else:
        _log("No NVIDIA model selected")

    cfg_path = paths.opencode_config / "opencode.json"
    write_opencode_config(cfg_path, model=selected_model)
    _log(f"Config: {cfg_path}")

    # --- Optional GitHub (temp credentials only) ---
    if github_repo:
        try:
            init_repo(paths.workspace)
            configure_remote(paths.workspace, github_repo)
            _log(f"GitHub remote: {github_repo}")
        except Exception as e:
            _log(f"GitHub setup skipped: {e}")

    # --- Start OpenCode ---
    env = os.environ.copy()
    env["NVIDIA_API_KEY"] = nvidia_key
    for v in (
        "OPENCODE_SERVER_PASSWORD",
        "OPENCODE_SERVER_USERNAME",
        "OPENCODE_SERVER_AUTH",
        "OPENCODE_PASSWORD",
        "OPENCODE_USERNAME",
    ):
        env.pop(v, None)

    log_path = paths.logs / "opencode-web.log"

    def start_proc():
        return start_opencode_web(
            opencode_bin,
            paths.workspace,
            port=opencode_port,
            env=env,
            log_path=log_path,
        )

    state = {"proc": start_proc()}
    _log(f"OpenCode PID {state['proc'].pid}")
    _log(describe_opencode_web_access(opencode_port))

    # --- Checkpoint manager ---
    ckpt = CheckpointManager(policy or CheckpointPolicy())

    def local_checkpoint(extra: Optional[dict] = None) -> dict:
        meta = store.save_local(
            opencode_data=paths.opencode_data,
            opencode_config=paths.opencode_config,
            workspace=paths.workspace,
            extra_meta=extra,
        )
        ckpt.record_local_checkpoint()
        return meta

    def remote_checkpoint(reason: PublishReason, notes: str = "") -> dict:
        should, decided = ckpt.should_publish_remote(reason=reason)
        if reason in (PublishReason.EXPLICIT, PublishReason.SHUTDOWN):
            should = True
            decided = reason
        if not should:
            return {"published": False, "reason": decided.value}

        local_checkpoint({"trigger": decided.value})
        ok, msg = persistence.publish_from_store(
            store, version_notes=notes or f"checkpoint:{decided.value}"
        )
        if ok:
            ckpt.record_remote_publish()
            if github_repo and github_token:
                try:
                    sync_to_remote(
                        paths.workspace,
                        f"OpenCode checkpoint ({decided.value})",
                        token=github_token,
                    )
                except Exception as e:
                    _log(f"GitHub sync warning: {e}")
        return {"published": ok, "message": msg, "reason": decided.value}

    # Initial local save
    local_checkpoint({"phase": "bootstrap"})
    if recovery.status == RecoveryStatus.FRESH_WORKSTATION:
        # First remote publish so Dataset exists for next runtime
        remote_checkpoint(PublishReason.EXPLICIT, notes="initial workstation")

    # --- Watchdog: REAL restart only (no Dataset publish, no git) ---
    def restart_and_track():
        _log("Watchdog: restarting OpenCode...")
        new_p = start_proc()
        state["proc"] = new_p
        _log(f"Watchdog: new PID {new_p.pid}")
        return new_p

    watchdog = Watchdog(
        check_interval=30,
        restart_fn=restart_and_track,
        process_poll=lambda: state["proc"].poll(),
    )
    watchdog.set_process(state["proc"])
    watchdog.start()

    # Shutdown hook → remote checkpoint
    def _on_shutdown(signum=None, frame=None):
        _log("Shutdown: remote checkpoint...")
        try:
            remote_checkpoint(PublishReason.SHUTDOWN, notes="shutdown")
        except Exception as e:
            _log(f"Shutdown checkpoint error: {e}")

    try:
        signal.signal(signal.SIGTERM, _on_shutdown)
        signal.signal(signal.SIGINT, _on_shutdown)
    except Exception:
        pass

    info = {
        "ok": True,
        "runtime": "kaggle",
        "recovery": recovery.status.value,
        "workspace": str(paths.workspace),
        "cloud_root": str(paths.cloud_root),
        "opencode_port": opencode_port,
        "opencode_pid": state["proc"].pid,
        "model": selected_model,
        "dataset_id": did,
        "web_access": describe_opencode_web_access(opencode_port),
        "checkpoint_state": ckpt.get_state(),
        "watchdog": watchdog.status(),
    }
    return info
