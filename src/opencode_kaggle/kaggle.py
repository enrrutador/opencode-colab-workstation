"""Kaggle-specific persistence adapters.

This module provides concrete implementations for Kaggle-native
persistence using Kaggle Datasets as the persistent store.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from opencode_cloud.persistence import PersistentStore


def detect_kaggle_dataset(dataset_id: Optional[str] = None) -> Path:
    """Detect the Kaggle dataset path from environment or explicit id.

    Kaggle kernels expose datasets under /kaggle/input/<dataset>.
    For persistence we prefer a user-owned dataset exported via
    Kaggle API. This helper returns the path to a persistent dataset
    if available.

    Environment variables to consider:
    - OPENCODE_CLOUD_DATASET: 'owner/dataset' id.
    - KAGGLE_DATASET_ID: legacy.

    Returns a Path to /kaggle/datasets/owner/dataset.
    """
    if dataset_id is None:
        dataset_id = (
            os.environ.get("OPENCODE_CLOUD_DATASET")
            or os.environ.get("KAGGLE_DATASET_ID")
        )

    if not dataset_id:
        raise RuntimeError(
            "Kaggle dataset not configured. Set OPENCODE_CLOUD_DATASET to 'owner/dataset'."
        )

    # Kaggle datasets are accessible via API for write operations. For
    # kernels, the read-only path is /kaggle/input. However, Kaggle
    # supports mutable datasets through the Kaggle API which writes
    # to /kaggle/working for staging and then publishes. This adapter
    # uses a convention where persistent data is staged in /kaggle/working
    # and synced via Kaggle API to the dataset.

    parts = dataset_id.split("/")
    if len(parts) != 2:
        raise ValueError("OPENCODE_CLOUD_DATASET must be in form 'owner/dataset'.")

    dataset_path = Path("/kaggle/datasets") / parts[0] / parts[1]
    if not dataset_path.exists():
        # Fallback: create a local staging area inside /kaggle/working
        # This will not persist across runtimes, but allows dry runs.
        staging_root = Path("/kaggle/working") / "opencode_cloud_persistent"
        staging_root.mkdir(parents=True, exist_ok=True)
        return staging_root

    return dataset_path


def get_kaggle_persistent_store(dataset_id: Optional[str] = None) -> PersistentStore:
    """Create a PersistentStore backed by a Kaggle dataset.

    Args:
        dataset_id: 'owner/dataset'. Auto-detected from environment if omitted.

    Returns:
        PersistentStore instance configured for Kaggle.
    """
    dataset_path = detect_kaggle_dataset(dataset_id)
    return PersistentStore(dataset_root=dataset_path)


def stage_for_publish(source: Path, staging_dir: Path) -> Path:
    """Stage files for Kaggle dataset publish.

    Kaggle datasets are typically updated via the Kaggle API. This helper
    ensures the source is copied to a staging directory ready for API upload.
    """
    staging_dir = Path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    # Use rsync to mirror source into staging
    import subprocess

    subprocess.run(["rsync", "-a", "--delete", f"{source}/", f"{staging_dir}/"], check=False)
    return staging_dir