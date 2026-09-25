"""Top-level bootstrap for OpenCode Cloud Workstation on Kaggle.

Phone flow:
  Kaggle notebook → bootstrap() → OpenCode + Kaggle Jupyter Proxy (HTTP-probed) → URL
"""

from __future__ import annotations

import json
import os
import signal
import threading
from pathlib import Path
from typing import Optional

from opencode_cloud.access import KaggleProxyAccess, format_workstation_banner, wait_for_port
from opencode_cloud.ports import get_opencode_port
from opencode_cloud.checkpoint import CheckpointManager, CheckpointPolicy, PublishReason
from opencode_cloud.github_sync import configure_remote, init_repo
from opencode_cloud.nvidia import fetch_models, select_model
from opencode_cloud.opencode import (
    ensure_node,
    ensure_opencode,
    start_opencode_web,
    write_opencode_config,
)
from opencode_cloud.persistence import KagglePersistence, RecoveryStatus, default_store
from opencode_cloud.runtime import ensure_dirs, get_paths, is_kaggle
from opencode_cloud.scheduler import CheckpointScheduler
from opencode_cloud.secrets import load_required_secret, load_secret
from opencode_cloud.watchdog import Watchdog
from opencode_kaggle.kaggle import resolve_dataset_id


def _log(msg: str) -> None:
    print(f"[OpenCode Cloud] {msg}")


def bootstrap(
    dataset_id: Optional[str] = None,
    opencode_port: Optional[int] = None,
    policy: Optional[CheckpointPolicy] = None,
    *,
    enable_access_layer: bool = True,
) -> dict:
    """Bootstrap the workstation. Returns runtime info including web_access."""
    if opencode_port is None:
        opencode_port = get_opencode_port()
    if not is_kaggle():
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

    nvidia_key = load_required_secret("NVIDIA_API_KEY")
    github_repo = load_secret("GITHUB_REPO")
    _ = load_secret("GITHUB_TOKEN")
    server_password = load_secret("OPENCODE_SERVER_PASSWORD") or ""
    server_username = load_secret("OPENCODE_SERVER_USERNAME") or "opencode"

    try:
        did = resolve_dataset_id(dataset_id)
    except Exception as e:
        raise RuntimeError(f"Dataset configuration error: {e}") from e

    persistence = KagglePersistence(did, paths.working)

    recovery = persistence.recover_into(store)
    _log(f"Recovery: {recovery.status.value} — {recovery.message}")

    if recovery.status == RecoveryStatus.RESTORE_FAILED:
        return {
            "ok": False,
            "status": "RESTORE_FAILED",
            "runtime": "kaggle",
            "recovery": recovery.status.value,
            "message": recovery.message,
        }

    store.restore_to(
        opencode_data=paths.opencode_data,
        opencode_config=paths.opencode_config,
        workspace=paths.workspace,
    )

    node_ver = ensure_node()
    _log(f"Node: {node_ver}")
    opencode_bin = ensure_opencode()
    _log(f"OpenCode: {opencode_bin}")

    models = fetch_models(nvidia_key)
    preferred = ""
    meta_path = store.metadata_dir / "nvidia.json"
    if meta_path.exists():
        try:
            preferred = json.loads(meta_path.read_text(encoding="utf-8")).get("model", "")
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

    if github_repo:
        try:
            init_repo(paths.workspace)
            configure_remote(paths.workspace, github_repo)
            _log(f"GitHub remote configured: {github_repo}")
        except Exception as e:
            _log(f"GitHub setup skipped: {e}")

    env = os.environ.copy()
    env["NVIDIA_API_KEY"] = nvidia_key
    if server_password:
        env["OPENCODE_SERVER_PASSWORD"] = server_password
        env["OPENCODE_SERVER_USERNAME"] = server_username
        _log("OpenCode basic auth: enabled (password from Secrets, not printed)")

    log_path = paths.logs / "opencode-web.log"

    def start_proc():
        return start_opencode_web(
            opencode_bin,
            paths.workspace,
            port=opencode_port,
            env=env,
            log_path=log_path,
        )

    state = {"proc": start_proc(), "access": None}
    _log(f"OpenCode PID {state['proc'].pid}")

    if not wait_for_port("127.0.0.1", opencode_port, timeout=90.0):
        return {
            "ok": False,
            "status": "BOOTSTRAP_FAILED",
            "runtime": "kaggle",
            "recovery": recovery.status.value,
            "message": f"OpenCode process started but port {opencode_port} is not listening",
            "opencode_pid": state["proc"].pid,
        }

    _log(f"OpenCode is listening on 127.0.0.1:{opencode_port}")

    access_info = {
        "available": False,
        "url": None,
        "status": "disabled",
        "message": "Access layer disabled",
        "local_port": opencode_port,
        "opencode_listening": True,
        "proxy_url_generated": False,
        "proxy_reachable": False,
        "authentication": "jupyter_session",
    }

    if enable_access_layer:
        info = KaggleProxyAccess(opencode_port).resolve()
        access_info = info.to_dict(include_url=True)
        state["access"] = info
        _log(
            format_workstation_banner(
                recovery=recovery.status.value,
                opencode_status="RUNNING" if info.opencode_listening else "NOT_RUNNING",
                access=info,
            )
        )
        if not info.available:
            access_info["status"] = (
                "OPENCODE_RUNNING_PROXY_UNAVAILABLE"
                if info.opencode_listening
                else "OPENCODE_NOT_RUNNING"
            )

    ckpt = CheckpointManager(policy or CheckpointPolicy())
    ckpt.set_baseline_fingerprint(paths.workspace)
    checkpoint_lock = threading.Lock()

    def local_checkpoint(extra: Optional[dict] = None) -> dict:
        meta = store.save_local(
            opencode_data=paths.opencode_data,
            opencode_config=paths.opencode_config,
            workspace=paths.workspace,
            extra_meta=extra,
        )
        ckpt.record_local_checkpoint()
        ckpt.set_baseline_fingerprint(paths.workspace)
        return meta

    def remote_checkpoint(reason: PublishReason, notes: str = "") -> dict:
        if reason not in (PublishReason.EXPLICIT, PublishReason.SHUTDOWN):
            ckpt.observe_workspace(paths.workspace)
        should, decided = ckpt.should_publish_remote(reason=reason)
        if reason in (PublishReason.EXPLICIT, PublishReason.SHUTDOWN):
            should = True
            decided = reason
        if not should:
            return {"published": False, "reason": decided.value}
        store.ensure_structure()
        store.write_marker({"phase": decided.value})
        validation = store.validate_workstation()
        if not validation.get("ok"):
            return {
                "published": False,
                "reason": "invalid_workstation",
                "message": validation.get("message"),
            }
        local_checkpoint({"trigger": decided.value})
        ok, msg = persistence.publish_from_store(
            store, version_notes=notes or f"checkpoint:{decided.value}"
        )
        if ok:
            ckpt.record_remote_publish()
        return {"published": ok, "message": msg, "reason": decided.value}

    local_checkpoint({"phase": "bootstrap"})
    if recovery.status == RecoveryStatus.FRESH_WORKSTATION:
        validation = store.validate_workstation()
        if validation.get("ok"):
            remote_checkpoint(PublishReason.EXPLICIT, notes="initial workstation")
        else:
            _log(f"Skipping initial publish: {validation.get('message')}")

    def restart_and_track():
        _log("Watchdog: restarting OpenCode...")
        new_p = start_proc()
        state["proc"] = new_p
        if wait_for_port("127.0.0.1", opencode_port, timeout=60.0):
            _log(f"Watchdog: OpenCode listening again (PID {new_p.pid})")
            try:
                reval = KaggleProxyAccess(opencode_port).resolve()
                state["access"] = reval
                _log(
                    f"Watchdog: access revalidate status={reval.status} "
                    f"reachable={reval.proxy_reachable} "
                    f"url={reval.url_redacted or 'n/a'}"
                )
            except Exception as e:
                _log(f"Watchdog: access revalidate failed: {type(e).__name__}")
        else:
            _log("Watchdog: OpenCode restarted but port not listening yet")
        return new_p

    watchdog = Watchdog(
        check_interval=30,
        restart_fn=restart_and_track,
        process_poll=lambda: state["proc"].poll(),
    )
    watchdog.set_process(state["proc"])
    watchdog.start()

    scheduler = CheckpointScheduler(
        ckpt,
        observe_fn=lambda: ckpt.observe_workspace(paths.workspace),
        local_fn=lambda: local_checkpoint({"trigger": "scheduler"}),
        remote_fn=lambda reason: remote_checkpoint(reason),
        lock=checkpoint_lock,
        interval=ckpt.policy.local_interval,
    )
    scheduler.start()
    _log(
        f"CheckpointScheduler started "
        f"(local every {ckpt.policy.local_interval}s, "
        f"remote min {ckpt.policy.min_publish_interval}s)"
    )

    def _on_shutdown(signum=None, frame=None):
        _log("Shutdown: final Dataset checkpoint")
        try:
            scheduler.shutdown_checkpoint()
        except Exception as e:
            _log(f"Shutdown checkpoint error: {e}")

    try:
        signal.signal(signal.SIGTERM, _on_shutdown)
        signal.signal(signal.SIGINT, _on_shutdown)
    except Exception:
        pass

    status = "READY"
    if not access_info.get("available") and enable_access_layer:
        status = "OPENCODE_RUNNING_PROXY_UNAVAILABLE"

    return {
        "ok": True,
        "status": status,
        "runtime": "kaggle",
        "recovery": recovery.status.value,
        "workspace": str(paths.workspace),
        "cloud_root": str(paths.cloud_root),
        "opencode_port": opencode_port,
        "opencode_pid": state["proc"].pid,
        "model": selected_model,
        "dataset_id": did,
        "web_access": access_info,
        "checkpoint_state": ckpt.get_state(),
        "watchdog": watchdog.status(),
        "scheduler": scheduler.status(),
        "rpo_target_seconds": ckpt.policy.min_publish_interval,
    }
