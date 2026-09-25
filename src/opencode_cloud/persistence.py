"""Persistence layer for OpenCode Cloud Workstation on Kaggle.

Design:
- Runtime state is ephemeral in /kaggle/working.
- Persistent state lives in a Kaggle Dataset, accessed via kagglehub.
- No direct writes to /kaggle/datasets/... The dataset is read-only via download
  and write-only via upload from staging.

Workflow:
- restore(): download Dataset → /kaggle/working/opencode_cloud/restore → copy to runtime paths
- stage(): copy runtime paths → /kaggle/working/opencode_cloud/staging
- publish(): upload staging to Dataset via kagglehub.dataset_upload
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class KagglePersistence:
    """Kaggle Dataset-backed persistence with staging."""

    def __init__(self, dataset_id: str, working_root: Path):
        if "/" not in dataset_id:
            raise ValueError("dataset_id must be 'owner/dataset'")
        self.dataset_id = dataset_id
        self.working_root = Path(working_root)
        self.staging_dir = self.working_root / "opencode_cloud" / "staging"
        self.restore_dir = self.working_root / "opencode_cloud" / "restore"
        self.metadata_path = self.staging_dir / "metadata.json"
        for d in [self.staging_dir, self.restore_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ---------- Helpers ----------
    def _ensure_kagglehub(self):
        try:
            import kagglehub  # type: ignore
            return kagglehub
        except ImportError as e:
            raise RuntimeError("kagglehub is required for Kaggle persistence") from e

    def ensure_structure(self) -> None:
        """Ensure staging layout exists."""
        for sub in ("state/opencode", "state/config", "workspace", "logs", "checkpoints"):
            (self.staging_dir / sub).mkdir(parents=True, exist_ok=True)

    # ---------- Restore ----------
    def download_dataset(self, target: Path) -> bool:
        """Download Dataset via kagglehub. Returns True if downloaded."""
        kagglehub = self._ensure_kagglehub()
        try:
            # kagglehub.dataset_download returns path to downloaded location
            downloaded = kagglehub.dataset_download(self.dataset_id)
            downloaded_path = Path(downloaded)
            if downloaded_path.exists():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(downloaded_path, target)
                return True
        except Exception:
            # Dataset may not exist yet
            pass
        return False

    def restore(self, paths) -> dict:
        """Restore runtime paths from Dataset.

        Args:
            paths: object with attributes opencode_data, opencode_config, workspace

        Returns:
            dict with status info.
        """
        self.ensure_structure()
        downloaded = self.download_dataset(self.restore_dir)
        restored = False
        if downloaded and any(self.restore_dir.iterdir()):
            # Restore state/opencode
            src = self.restore_dir / "state" / "opencode"
            if src.exists():
                shutil.copytree(src, paths.opencode_data, dirs_exist_ok=True)
            src = self.restore_dir / "state" / "config"
            if src.exists():
                shutil.copytree(src, paths.opencode_config, dirs_exist_ok=True)
            src = self.restore_dir / "workspace"
            if src.exists():
                shutil.copytree(src, paths.workspace, dirs_exist_ok=True)
            restored = True

        return {
            "restored_from_dataset": restored,
            "dataset_id": self.dataset_id,
        }

    # ---------- Stage ----------
    def stage(self, paths, checkpoint_manager=None) -> dict:
        """Stage current runtime state into staging directory."""
        self.ensure_structure()
        # Copy from runtime to staging
        shutil.copytree(paths.opencode_data, self.staging_dir / "state" / "opencode", dirs_exist_ok=True)
        shutil.copytree(paths.opencode_config, self.staging_dir / "state" / "config", dirs_exist_ok=True)
        shutil.copytree(paths.workspace, self.staging_dir / "workspace", dirs_exist_ok=True)
        # Save metadata
        meta = {
            "staged_at": datetime.utcnow().isoformat() + "Z",
            "dataset_id": self.dataset_id,
        }
        try:
            import json
            self.metadata_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass
        return meta

    # ---------- Publish ----------
    def publish(self) -> dict:
        """Publish staging directory to Kaggle Dataset.

        Returns dict with status.
        """
        if not self.staging_dir.exists() or not any(self.staging_dir.iterdir()):
            return {"published": False, "reason": "staging empty"}

        kagglehub = self._ensure_kagglehub()
        try:
            # kagglehub.dataset_upload expects a local directory path
            # and a dataset name in owner/dataset format
            # Note: actual API may differ; this is the intended usage.
            kagglehub.dataset_upload(self.staging_dir, self.dataset_id)
            return {"published": True, "dataset_id": self.dataset_id}
        except Exception as e:
            # Do not delete staging on failure
            return {"published": False, "error": str(e)}

    # ---------- Metadata ----------
    def has_dataset(self) -> bool:
        """Check if Dataset can be downloaded."""
        return self.download_dataset(self.restore_dir)

    def latest_metadata(self) -> Optional[dict]:
        """Return metadata from last staging."""
        if self.metadata_path.exists():
            try:
                return json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None


class PersistentStore:
    """Legacy wrapper for backward compatibility.

    Delegates to KagglePersistence with a working root.
    """

    def __init__(self, dataset_id: Optional[str] = None, dataset_root: Optional[Path] = None):
        self.dataset_id = dataset_id or ""
        self.dataset_root = dataset_root
        # Use working root as fallback
        self._kaggle = None

    def _get_kaggle(self):
        if self._kaggle is None:
            if not self.dataset_id:
                raise RuntimeError("dataset_id not configured")
            from .runtime import get_paths
            paths = get_paths("kaggle")
            self._kaggle = KagglePersistence(self.dataset_id, paths.working)
        return self._kaggle

    def ensure_structure(self) -> None:
        self._get_kaggle().ensure_structure()

    def restore(self, paths):  # type: ignore
        return self._get_kaggle().restore(paths)

    def stage(self, paths, checkpoint_manager=None):  # type: ignore
        return self._get_kaggle().stage(paths)

    def publish(self):
        return self._get_kaggle().publish()


def default_store(dataset_id: Optional[str] = None) -> KagglePersistence:
    import os
    from .runtime import get_paths
    dataset_id = dataset_id or os.environ.get("OPENCODE_CLOUD_DATASET")
    if not dataset_id:
        raise RuntimeError("OPENCODE_CLOUD_DATASET not configured")
    paths = get_paths("kaggle")
    return KagglePersistence(dataset_id, paths.working)