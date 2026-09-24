"""Persistence layer for OpenCode Cloud Workstation.

Design principles:
- Runtime state is ephemeral and may disappear at any time.
- Persistent state lives in:
  * Kaggle Dataset (workspace, opencode state, config, logs, checkpoints)
  * GitHub (source code, version history)
  * Kaggle Models (model artifacts, when applicable)
  * Kaggle Secrets (credentials)
- This module abstracts the persistent store so the rest of the codebase
  does not need to know where data lives.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class PersistentStore:
    """Abstraction over the persistent storage backend."""

    dataset_id: Optional[str] = None
    dataset_root: Optional[Path] = None

    def __post_init__(self):
        if self.dataset_root is None and self.dataset_id:
            # Kaggle datasets are mounted under /kaggle/datasets/<owner>/<dataset>
            parts = self.dataset_id.split("/")
            if len(parts) == 2:
                self.dataset_root = Path("/kaggle/datasets") / parts[0] / parts[1]

    @property
    def root(self) -> Path:
        if self.dataset_root is None:
            raise RuntimeError("PersistentStore is not configured with a dataset_root.")
        return self.dataset_root

    def ensure_structure(self) -> None:
        """Create the standard directory layout inside the persistent store."""
        for sub in (
            "state/opencode",
            "state/config",
            "state/runtime",
            "workspace",
            "backups",
            "logs",
            "checkpoints",
        ):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def write_json(self, rel_path: str, data: Any) -> None:
        p = self.path(rel_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_json(self, rel_path: str, default: Any = None) -> Any:
        p = self.path(rel_path)
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default

    def sync_from(self, source: Path, rel_dest: str, delete: bool = False) -> None:
        """Sync a local directory into the persistent store."""
        source = Path(source)
        dest = self.path(rel_dest)
        if not source.exists():
            return
        dest.mkdir(parents=True, exist_ok=True)
        cmd = ["rsync", "-a"]
        if delete:
            cmd.append("--delete")
        cmd.extend([f"{source}/", f"{dest}/"])
        import subprocess

        subprocess.run(cmd, check=False)

    def sync_to(self, rel_source: str, destination: Path, delete: bool = False) -> None:
        """Sync from the persistent store to a local directory."""
        source = self.path(rel_source)
        destination = Path(destination)
        if not source.exists():
            return
        destination.mkdir(parents=True, exist_ok=True)
        cmd = ["rsync", "-a"]
        if delete:
            cmd.append("--delete")
        cmd.extend([f"{source}/", f"{destination}/"])
        import subprocess

        subprocess.run(cmd, check=False)

    def has_files(self, rel_path: str) -> bool:
        p = self.path(rel_path)
        if not p.exists():
            return False
        try:
            return any(p.iterdir())
        except Exception:
            return False

    def list_checkpoints(self) -> list[Path]:
        cp_dir = self.path("checkpoints")
        if not cp_dir.exists():
            return []
        return sorted(cp_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)

    def save_checkpoint(self, label: str, metadata: dict) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cp_path = self.path("checkpoints", f"{ts}_{label}.json")
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        cp_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return cp_path


def default_store(dataset_id: Optional[str] = None) -> PersistentStore:
    """Create a PersistentStore using the configured Kaggle dataset."""
    dataset_id = dataset_id or os.environ.get("OPENCODE_CLOUD_DATASET")
    return PersistentStore(dataset_id=dataset_id)