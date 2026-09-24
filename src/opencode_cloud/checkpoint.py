"""Checkpoint strategy for OpenCode Cloud Workstation.

Two distinct concepts:

1. Local checkpoint:
   - Fast, frequent, in-memory or local-disk snapshot.
   - Used to survive process crashes and OpenCode restarts.
   - Does NOT trigger a remote publish.

2. Remote persistence:
   - Publish state to the persistent store (Kaggle Dataset).
   - Triggered by a policy, not by a fixed timer.
   - Policy criteria:
     * Minimum interval elapsed since last publish.
     * Significant changes detected (workspace diff, config change).
     * Ordered shutdown requested.
     * Explicit checkpoint request.
     * Recovery scenario.
     * Important workspace event (e.g., git commit).

This module implements the decision logic only; the actual sync is
delegated to the persistence layer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


# Default policy constants
MIN_PUBLISH_INTERVAL_SECONDS = 300  # 5 minutes minimum between remote publishes
MIN_CHANGES_FOR_PUBLISH = 1  # At least one meaningful change


@dataclass
class CheckpointPolicy:
    """Policy controlling when to publish a remote checkpoint."""

    min_publish_interval: int = MIN_PUBLISH_INTERVAL_SECONDS
    min_changes: int = MIN_CHANGES_FOR_PUBLISH
    always_on_shutdown: bool = True
    always_on_recovery: bool = True
    always_on_explicit: bool = True


@dataclass
class CheckpointState:
    """Tracks checkpoint-related state across bootstrap runs."""

    last_local_checkpoint: float = 0.0
    last_remote_publish: float = 0.0
    remote_publish_count: int = 0
    pending_significant_changes: int = 0


class CheckpointManager:
    """Decides when to perform local checkpoints and remote publishes."""

    def __init__(self, policy: Optional[CheckpointPolicy] = None):
        self.policy = policy or CheckpointPolicy()
        self.state = CheckpointState()

    def request_local(self) -> bool:
        """Request a local checkpoint. Always allowed."""
        self.state.last_local_checkpoint = time.time()
        return True

    def request_explicit_remote(self) -> bool:
        """Request an explicit remote publish. Always allowed by policy."""
        self.state.last_remote_publish = time.time()
        self.state.remote_publish_count += 1
        self.state.pending_significant_changes = 0
        return True

    def request_remote_on_shutdown(self) -> bool:
        """Request remote publish during ordered shutdown."""
        if self.policy.always_on_shutdown:
            return self.request_explicit_remote()
        return False

    def request_remote_on_recovery(self) -> bool:
        """Request remote publish during recovery."""
        if self.policy.always_on_recovery:
            return self.request_explicit_remote()
        return False

    def should_publish(self, significant_changes: int = 0) -> bool:
        """Decide whether a remote publish should happen now."""
        now = time.time()
        elapsed = now - self.state.last_remote_publish

        # Always publish if minimum interval has passed and there are changes.
        if significant_changes >= self.policy.min_changes and elapsed >= self.policy.min_publish_interval:
            self.state.last_remote_publish = now
            self.state.remote_publish_count += 1
            self.state.pending_significant_changes = 0
            return True

        return False

    def mark_significant_change(self) -> None:
        self.state.pending_significant_changes += 1

    def get_state(self) -> dict:
        return {
            "last_local_checkpoint": self.state.last_local_checkpoint,
            "last_remote_publish": self.state.last_remote_publish,
            "remote_publish_count": self.state.remote_publish_count,
            "pending_significant_changes": self.state.pending_significant_changes,
        }