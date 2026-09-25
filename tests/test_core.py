"""Significant tests for OpenCode Cloud Workstation architecture.

Runnable outside Kaggle with mocks. No sys.path hacks when installed editable;
path bootstrap only for direct script runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src is importable when running without install
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in os.sys.path:
    os.sys.path.insert(0, str(_SRC))


def test_no_colab_references_in_source():
    root = Path(__file__).resolve().parents[1] / "src"
    forbidden = [
        "google.colab",
        "drive.mount",
        "/content/",
        "MyDrive",
        "is_colab",
        "from google.colab",
    ]
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")
    assert not offenders, f"Colab leftovers: {offenders}"


def test_no_shell_true_in_source():
    root = Path(__file__).resolve().parents[1] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "shell=True" in text:
            offenders.append(str(path))
    assert not offenders, f"shell=True found in: {offenders}"


def test_persistent_store_never_writes_kaggle_datasets():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "opencode_cloud"
        from opencode_cloud.persistence import PersistentStore

        store = PersistentStore(root)
        store.ensure_structure()
        assert store.never_writes_to_kaggle_datasets()
        assert not str(store.root).startswith("/kaggle/datasets")


def test_persistent_store_local_save_and_restore():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import PersistentStore

        store = PersistentStore(tmp / "opencode_cloud")
        oc_data = tmp / "oc_data"
        oc_cfg = tmp / "oc_cfg"
        ws = tmp / "ws"
        for d in (oc_data, oc_cfg, ws):
            d.mkdir()
            (d / "file.txt").write_text("hello", encoding="utf-8")

        meta = store.save_local(
            opencode_data=oc_data, opencode_config=oc_cfg, workspace=ws
        )
        assert "saved_at" in meta
        assert store.is_valid_workstation()

        out_data = tmp / "out_data"
        out_cfg = tmp / "out_cfg"
        out_ws = tmp / "out_ws"
        ok = store.restore_to(
            opencode_data=out_data, opencode_config=out_cfg, workspace=out_ws
        )
        assert ok
        assert (out_ws / "file.txt").read_text(encoding="utf-8") == "hello"


def test_prepare_staging_contains_marker():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import PersistentStore

        store = PersistentStore(tmp / "opencode_cloud")
        oc = tmp / "oc"
        oc.mkdir()
        (oc / "x").write_text("1", encoding="utf-8")
        store.save_local(opencode_data=oc, opencode_config=oc, workspace=oc)
        staging = store.prepare_staging()
        assert (staging / "workstation.json").exists()
        assert (staging / "workspace").exists()


def test_kaggle_persistence_download_calls_dataset_download():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import KagglePersistence

        kp = KagglePersistence("owner/ds", tmp)
        fake_path = tmp / "downloaded"
        fake_path.mkdir()
        (fake_path / "workstation.json").write_text(
            json.dumps({"kind": "opencode-cloud-workstation"}), encoding="utf-8"
        )
        (fake_path / "workspace").mkdir()

        mock_kh = MagicMock()
        mock_kh.dataset_download.return_value = str(fake_path)

        with patch.object(kp, "_kagglehub", return_value=mock_kh):
            ok, path, msg = kp.download()
        assert ok
        assert path == fake_path
        mock_kh.dataset_download.assert_called()
        args, kwargs = mock_kh.dataset_download.call_args
        assert args[0] == "owner/ds"


def test_kaggle_persistence_upload_calls_dataset_upload():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import KagglePersistence

        kp = KagglePersistence("owner/ds", tmp)
        staging = tmp / "staging"
        staging.mkdir()
        (staging / "workstation.json").write_text("{}", encoding="utf-8")

        mock_kh = MagicMock()
        with patch.object(kp, "_kagglehub", return_value=mock_kh):
            ok, msg = kp.upload(staging, version_notes="test")
        assert ok
        mock_kh.dataset_upload.assert_called_once()
        args, kwargs = mock_kh.dataset_upload.call_args
        assert args[0] == "owner/ds"
        assert str(staging) in args[1]


def test_kaggle_persistence_download_missing_dataset():
    with tempfile.TemporaryDirectory() as tmp:
        from opencode_cloud.persistence import KagglePersistence

        kp = KagglePersistence("owner/missing", Path(tmp))
        mock_kh = MagicMock()
        mock_kh.dataset_download.side_effect = Exception("404 Not Found")

        with patch.object(kp, "_kagglehub", return_value=mock_kh):
            ok, path, msg = kp.download()
        assert not ok
        assert path is None
        assert "does not exist" in msg.lower() or "not found" in msg.lower()


def test_recovery_fresh_when_dataset_missing():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import (
            KagglePersistence,
            PersistentStore,
            RecoveryStatus,
        )

        store = PersistentStore(tmp / "opencode_cloud")
        store.ensure_structure()
        kp = KagglePersistence("owner/missing", tmp)
        mock_kh = MagicMock()
        mock_kh.dataset_download.side_effect = Exception("404 dataset not found")

        with patch.object(kp, "_kagglehub", return_value=mock_kh):
            result = kp.recover_into(store)
        assert result.status == RecoveryStatus.FRESH_WORKSTATION


def test_recovery_restored_from_valid_dataset():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import (
            KagglePersistence,
            PersistentStore,
            RecoveryStatus,
        )

        store = PersistentStore(tmp / "opencode_cloud")
        store.ensure_structure()

        download = tmp / "dl"
        download.mkdir()
        (download / "workstation.json").write_text(
            json.dumps({"kind": "opencode-cloud-workstation"}), encoding="utf-8"
        )
        (download / "workspace").mkdir()
        (download / "workspace" / "code.py").write_text("print(1)", encoding="utf-8")

        kp = KagglePersistence("owner/ds", tmp)
        mock_kh = MagicMock()
        mock_kh.dataset_download.return_value = str(download)

        with patch.object(kp, "_kagglehub", return_value=mock_kh):
            result = kp.recover_into(store)
        assert result.status == RecoveryStatus.RESTORED_FROM_DATASET
        assert (store.workspace / "code.py").exists()


def test_recovery_failed_on_corrupt():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        from opencode_cloud.persistence import (
            KagglePersistence,
            PersistentStore,
            RecoveryStatus,
        )

        store = PersistentStore(tmp / "opencode_cloud")
        download = tmp / "dl"
        download.mkdir()
        (download / "random.txt").write_text("not a workstation", encoding="utf-8")

        kp = KagglePersistence("owner/ds", tmp)
        mock_kh = MagicMock()
        mock_kh.dataset_download.return_value = str(download)

        with patch.object(kp, "_kagglehub", return_value=mock_kh):
            result = kp.recover_into(store)
        assert result.status == RecoveryStatus.RESTORE_FAILED


def test_checkpoint_local_always_allowed():
    from opencode_cloud.checkpoint import CheckpointManager

    mgr = CheckpointManager()
    mgr.record_local_checkpoint()
    assert mgr.state.last_local_checkpoint > 0


def test_checkpoint_cooldown_five_minutes():
    from opencode_cloud.checkpoint import CheckpointManager, PublishReason

    mgr = CheckpointManager()
    mgr.mark_significant_change()
    should, reason = mgr.should_publish_remote()
    assert should
    assert reason == PublishReason.COOLDOWN_AND_CHANGES

    mgr.record_remote_publish()
    mgr.mark_significant_change()
    should, reason = mgr.should_publish_remote()
    assert not should


def test_checkpoint_explicit_and_shutdown():
    from opencode_cloud.checkpoint import CheckpointManager, PublishReason

    mgr = CheckpointManager()
    mgr.record_remote_publish()
    should, reason = mgr.should_publish_remote(reason=PublishReason.EXPLICIT)
    assert should and reason == PublishReason.EXPLICIT
    should, reason = mgr.should_publish_remote(reason=PublishReason.SHUTDOWN)
    assert should and reason == PublishReason.SHUTDOWN


def test_watchdog_restarts_on_death():
    from opencode_cloud.watchdog import Watchdog

    calls = []

    class FakeProc:
        def __init__(self, dead=False):
            self._dead = dead

        def poll(self):
            return 1 if self._dead else None

    current = {"proc": FakeProc(dead=True)}

    def restart():
        calls.append("restart")
        p = FakeProc(dead=False)
        current["proc"] = p
        return p

    wd = Watchdog(
        check_interval=0,
        restart_fn=restart,
        process_poll=lambda: current["proc"].poll(),
    )
    wd.set_process(current["proc"])
    wd._do_restart()
    assert calls == ["restart"]
    assert wd.restart_count == 1
    assert wd.last_restart_ok is True


def test_watchdog_requires_real_restart_fn():
    from opencode_cloud.watchdog import Watchdog

    wd = Watchdog(restart_fn=None)
    with pytest.raises(RuntimeError):
        wd.start()


def test_secrets_env_fallback():
    from opencode_cloud.secrets import EnvSecrets

    mgr = EnvSecrets()
    assert mgr.get("NONEXISTENT_XYZ") is None
    os.environ["TEST_SECRET_XYZ"] = "value"
    try:
        assert mgr.get("TEST_SECRET_XYZ") == "value"
    finally:
        del os.environ["TEST_SECRET_XYZ"]


def test_kaggle_secrets_uses_user_secrets_client():
    from opencode_cloud.secrets import KaggleSecrets

    mock_client = MagicMock()
    mock_client.get_secret.return_value = "secret-value"

    with patch.dict("sys.modules", {"kaggle_secrets": MagicMock()}):
        import sys

        sys.modules["kaggle_secrets"].UserSecretsClient = MagicMock(
            return_value=mock_client
        )
        ks = KaggleSecrets.__new__(KaggleSecrets)
        ks._client = mock_client
        assert ks.get("NVIDIA_API_KEY") == "secret-value"
        mock_client.get_secret.assert_called_with("NVIDIA_API_KEY")


def test_github_credential_file_deleted_even_on_failure():
    from opencode_cloud.github_sync import temporary_credential_helper, init_repo

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "ws"
        init_repo(ws)
        seen = {}

        try:
            with temporary_credential_helper("fake-token", ws) as cred:
                seen["path"] = cred
                assert cred.exists()
                raise RuntimeError("simulate git failure")
        except RuntimeError:
            pass

        assert "path" in seen
        assert not seen["path"].exists()


def test_github_validate_url():
    from opencode_cloud.github_sync import validate_repo_url

    assert validate_repo_url("https://github.com/owner/repo").endswith(".git")
    with pytest.raises(ValueError):
        validate_repo_url("not-a-url")


def test_ensure_node_idempotent_when_present():
    from opencode_cloud.opencode import ensure_node

    import shutil

    if shutil.which("node"):
        ver = ensure_node()
        assert ver.startswith("v") or ver[0].isdigit()


def test_write_opencode_config_incremental():
    from opencode_cloud.opencode import write_opencode_config

    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "opencode.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "$schema": "https://opencode.ai/config.json",
                    "provider": {"other": {"name": "Other"}},
                    "permission": "ask",
                }
            ),
            encoding="utf-8",
        )
        write_opencode_config(cfg_path, model="nemotron-test")
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["permission"] == "allow"
        assert "nvidia" in data["provider"]
        assert "other" in data["provider"]
        assert data["model"] == "nvidia/nemotron-test"
        dumped = json.dumps(data)
        assert "nvapi-" not in dumped
        assert "{env:NVIDIA_API_KEY}" in dumped


def test_runtime_paths_kaggle_layout():
    from opencode_cloud.runtime import get_paths

    paths = get_paths("kaggle")
    assert paths.working == Path("/kaggle/working")
    assert paths.cloud_root == Path("/kaggle/working/opencode_cloud")
    assert paths.workspace == Path("/kaggle/working/opencode_cloud/workspace")
