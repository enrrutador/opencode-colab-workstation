"""Persistence layer for OpenCode Cloud Workstation on Kaggle.

Architecture (strict separation of responsibilities):

  PersistentStore
    → manages ONLY local ephemeral storage under /kaggle/working/opencode_cloud/
    → workspace, state, config, checkpoints, metadata, logs
    → NEVER publishes remotely

  KagglePersistence
    → manages ONLY interaction with Kaggle Dataset via kagglehub
    → dataset_download() / dataset_upload()
    → staging for upload; never treats /kaggle/datasets as writable FS

  CheckpointManager (in checkpoint.py)
    → decides WHEN to publish
    → does not perform the publish itself

Workflow:

  RECOVERY (new runtime):
    Kaggle Dataset
      → kagglehub.dataset_download()
      → restore staging
      → PersistentStore.restore_from()
      → /kaggle/working/opencode_cloud/

  CHECKPOINT remote:
    /kaggle/working/opencode_cloud/
      → PersistentStore.prepare_staging()
      → kagglehub.dataset_upload()
      → Kaggle Dataset
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class RecoveryStatus(str, Enum):
    """Outcome of a recovery attempt."""

    RESTORED_FROM_DATASET = "RESTORED_FROM_DATASET"
    FRESH_WORKSTATION = "FRESH_WORKSTATION"
    RESTORE_FAILED = "RESTORE_FAILED"


@dataclass
class RecoveryResult:
    status: RecoveryStatus
    dataset_id: str = ""
    message: str = ""
    details: Optional[dict] = None


class PersistentStore:
    """Local workstation store under /kaggle/working/opencode_cloud/.

    Never writes to /kaggle/datasets.
    Never calls kagglehub.
    """

    MARKER_FILE = "workstation.json"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.workspace = self.root / "workspace"
        self.state = self.root / "state"
        self.config = self.root / "config"
        self.checkpoints = self.root / "checkpoints"
        self.logs = self.root / "logs"
        self.metadata_dir = self.root / "metadata"
        self.staging = self.root / "staging"

    def ensure_structure(self) -> None:
        for d in (
            self.root,
            self.workspace,
            self.state,
            self.config,
            self.checkpoints,
            self.logs,
            self.metadata_dir,
            self.staging,
            self.state / "opencode",
            self.state / "config",
        ):
            d.mkdir(parents=True, exist_ok=True)

    def is_valid_workstation(self, path: Optional[Path] = None) -> bool:
        """Return True if path is a complete, schema-compatible workstation."""
        return self.validate_workstation(path).get("ok", False)

    def validate_workstation(self, path: Optional[Path] = None) -> dict:
        """Detailed workstation validation.

        Returns dict with keys:
          ok: bool
          status: valid | incomplete | incompatible | invalid
          message: human-readable reason
        """
        base = Path(path) if path is not None else self.root
        marker = base / self.MARKER_FILE
        if not marker.exists():
            return {
                "ok": False,
                "status": "incomplete",
                "message": "missing workstation.json marker",
            }
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except Exception as e:
            return {
                "ok": False,
                "status": "invalid",
                "message": f"marker unreadable: {type(e).__name__}",
            }
        if not isinstance(data, dict):
            return {"ok": False, "status": "invalid", "message": "marker is not an object"}
        if data.get("kind") != "opencode-cloud-workstation":
            return {
                "ok": False,
                "status": "incompatible",
                "message": f"unexpected kind: {data.get('kind')!r}",
            }
        version = str(data.get("version", ""))
        if not version.startswith("5."):
            return {
                "ok": False,
                "status": "incompatible",
                "message": f"incompatible schema version: {version!r}",
            }
        has_workspace = (base / "workspace").is_dir()
        has_state = (base / "state").is_dir()
        has_config = (base / "config").is_dir()
        if not has_workspace:
            return {
                "ok": False,
                "status": "incomplete",
                "message": "missing workspace/ directory",
            }
        if not (has_state or has_config):
            return {
                "ok": False,
                "status": "incomplete",
                "message": "missing state/ and config/",
            }
        return {"ok": True, "status": "valid", "message": "workstation ok", "version": version}

    def write_marker(self, extra: Optional[dict] = None) -> None:
        data = {
            "kind": "opencode-cloud-workstation",
            "version": "5.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            data.update(extra)
        self.ensure_structure()
        (self.root / self.MARKER_FILE).write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def save_local(
        self,
        *,
        opencode_data: Path,
        opencode_config: Path,
        workspace: Path,
        extra_meta: Optional[dict] = None,
    ) -> dict:
        """Copy runtime paths into the local store. Cheap local checkpoint."""
        self.ensure_structure()

        def _copy(src: Path, dst: Path) -> None:
            if not src.exists():
                return
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

        _copy(opencode_data, self.state / "opencode")
        _copy(opencode_config, self.state / "config")
        _copy(opencode_config, self.config)
        _copy(workspace, self.workspace)

        meta = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "kind": "local_checkpoint",
        }
        if extra_meta:
            meta.update(extra_meta)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        (self.metadata_dir / "last_local.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        self.write_marker(extra_meta)
        return meta

    def restore_to(
        self,
        *,
        opencode_data: Path,
        opencode_config: Path,
        workspace: Path,
        source: Optional[Path] = None,
    ) -> bool:
        """Restore runtime paths from this store (or from source path)."""
        base = Path(source) if source is not None else self.root
        restored_any = False

        def _restore(src: Path, dst: Path) -> bool:
            if not src.exists():
                return False
            try:
                if src.is_dir() and not any(src.iterdir()):
                    return False
            except Exception:
                return False
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            return True

        if _restore(base / "state" / "opencode", opencode_data):
            restored_any = True
        cfg_src = base / "state" / "config"
        if not cfg_src.exists():
            cfg_src = base / "config"
        if _restore(cfg_src, opencode_config):
            restored_any = True
        if _restore(base / "workspace", workspace):
            restored_any = True

        return restored_any

    def prepare_staging(self) -> Path:
        """Prepare staging directory for remote publish from current local store."""
        self.ensure_structure()
        if self.staging.exists():
            shutil.rmtree(self.staging)
        self.staging.mkdir(parents=True, exist_ok=True)

        for name in ("workspace", "state", "config", "checkpoints", "logs", "metadata"):
            src = self.root / name
            if src.exists():
                shutil.copytree(src, self.staging / name, dirs_exist_ok=True)

        marker_src = self.root / self.MARKER_FILE
        if marker_src.exists():
            shutil.copy2(marker_src, self.staging / self.MARKER_FILE)
        else:
            data = {
                "kind": "opencode-cloud-workstation",
                "version": "5.0.0",
                "staged_at": datetime.now(timezone.utc).isoformat(),
            }
            (self.staging / self.MARKER_FILE).write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )

        return self.staging

    def never_writes_to_kaggle_datasets(self) -> bool:
        """Guard used by tests: root must not be under /kaggle/datasets."""
        try:
            return not str(self.root.resolve()).startswith("/kaggle/datasets")
        except Exception:
            return not str(self.root).startswith("/kaggle/datasets")


class KagglePersistence:
    """Remote persistence via Kaggle Dataset using kagglehub.

    Does NOT treat /kaggle/datasets as a writable filesystem.
    """

    def __init__(self, dataset_id: str, working_root: Path):
        if not dataset_id or "/" not in dataset_id:
            raise ValueError("dataset_id must be 'owner/dataset'")
        if "/versions/" in dataset_id:
            raise ValueError("dataset_id must not include a version for upload")
        self.dataset_id = dataset_id
        self.working_root = Path(working_root)
        self.download_cache = self.working_root / "opencode_cloud_download"
        self.download_cache.mkdir(parents=True, exist_ok=True)

    def _kagglehub(self):
        try:
            import kagglehub  # type: ignore

            return kagglehub
        except ImportError as e:
            raise RuntimeError(
                "kagglehub is required for Kaggle Dataset persistence. "
                "Install with: pip install kagglehub"
            ) from e

    def download(self, force: bool = False) -> tuple[bool, Optional[Path], str]:
        """Download the Dataset via kagglehub.dataset_download."""
        kh = self._kagglehub()
        try:
            try:
                path_str = kh.dataset_download(
                    self.dataset_id,
                    output_dir=str(self.download_cache),
                    force_download=force,
                )
            except TypeError:
                path_str = kh.dataset_download(self.dataset_id, force_download=force)

            path = Path(path_str)
            if path.exists():
                return True, path, f"Downloaded to {path}"
            return False, None, f"Download returned non-existent path: {path_str}"
        except Exception as e:
            msg = str(e).lower()
            if any(
                token in msg
                for token in ("404", "not found", "does not exist", "not exist", "404 client")
            ):
                return False, None, f"Dataset does not exist yet: {self.dataset_id}"
            return False, None, f"Download failed: {e}"

    def upload(self, local_dir: Path, version_notes: str = "") -> tuple[bool, str]:
        """Upload local_dir as a new Dataset version via kagglehub.dataset_upload."""
        local_dir = Path(local_dir)
        if not local_dir.exists() or not any(local_dir.iterdir()):
            return False, "Staging directory is empty or missing"

        kh = self._kagglehub()
        try:
            kh.dataset_upload(
                self.dataset_id,
                str(local_dir),
                version_notes=version_notes or "OpenCode Cloud Workstation checkpoint",
            )
            return True, f"Published to {self.dataset_id}"
        except Exception as e:
            return False, f"Upload failed: {e}"

    def recover_into(self, store: PersistentStore) -> RecoveryResult:
        """Download Dataset and restore into the given PersistentStore."""
        ok, download_path, msg = self.download()
        if not ok or download_path is None:
            if "does not exist" in msg.lower() or "not found" in msg.lower():
                return RecoveryResult(
                    status=RecoveryStatus.FRESH_WORKSTATION,
                    dataset_id=self.dataset_id,
                    message=msg,
                )
            return RecoveryResult(
                status=RecoveryStatus.RESTORE_FAILED,
                dataset_id=self.dataset_id,
                message=msg,
            )

        if not store.is_valid_workstation(download_path):
            try:
                has_files = any(download_path.rglob("*"))
            except Exception:
                has_files = False
            if not has_files:
                return RecoveryResult(
                    status=RecoveryStatus.FRESH_WORKSTATION,
                    dataset_id=self.dataset_id,
                    message="Dataset exists but is empty; starting fresh",
                )
            return RecoveryResult(
                status=RecoveryStatus.RESTORE_FAILED,
                dataset_id=self.dataset_id,
                message="Downloaded Dataset does not contain a valid workstation marker",
                details={"path": str(download_path)},
            )

        try:
            snapshot = self.working_root / "opencode_cloud_restore_snapshot"
            if snapshot.exists():
                shutil.rmtree(snapshot)
            shutil.copytree(download_path, snapshot)

            if store.root.exists():
                for child in list(store.root.iterdir()):
                    if child.name in ("staging",):
                        continue
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            store.ensure_structure()

            for item in snapshot.iterdir():
                dest = store.root / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            if not store.is_valid_workstation():
                return RecoveryResult(
                    status=RecoveryStatus.RESTORE_FAILED,
                    dataset_id=self.dataset_id,
                    message="Copy completed but workstation validation failed",
                )

            return RecoveryResult(
                status=RecoveryStatus.RESTORED_FROM_DATASET,
                dataset_id=self.dataset_id,
                message=f"Restored from {download_path}",
                details={"path": str(download_path)},
            )
        except Exception as e:
            return RecoveryResult(
                status=RecoveryStatus.RESTORE_FAILED,
                dataset_id=self.dataset_id,
                message=f"Restore copy failed: {e}",
            )

    def publish_from_store(
        self, store: PersistentStore, version_notes: str = ""
    ) -> tuple[bool, str]:
        """Stage local store and upload to Dataset.

        Refuses to publish if the store fails workstation validation.
        """
        validation = store.validate_workstation()
        if not validation.get("ok"):
            return (
                False,
                f"refusing to publish invalid workstation: {validation.get('message')}",
            )
        staging = store.prepare_staging()
        return self.upload(staging, version_notes=version_notes)


def default_store(working: Optional[Path] = None) -> PersistentStore:
    """Create PersistentStore under /kaggle/working/opencode_cloud (or override)."""
    if working is None:
        from .runtime import get_paths

        working = get_paths().working
    root = Path(working) / "opencode_cloud"
    store = PersistentStore(root)
    store.ensure_structure()
    return store


def default_kaggle_persistence(
    dataset_id: Optional[str] = None, working: Optional[Path] = None
) -> KagglePersistence:
    import os

    dataset_id = dataset_id or os.environ.get("OPENCODE_CLOUD_DATASET")
    if not dataset_id:
        raise RuntimeError(
            "OPENCODE_CLOUD_DATASET not configured (expected 'owner/dataset')"
        )
    if working is None:
        from .runtime import get_paths

        working = get_paths().working
    return KagglePersistence(dataset_id, Path(working))
