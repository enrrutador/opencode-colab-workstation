"""Checkpoint strategy for OpenCode Cloud Workstation.

Two levels:

1. Local checkpoint (cheap, frequent)
   - Saved under /kaggle/working/opencode_cloud/
   - Does NOT create a Dataset version

2. Remote checkpoint (expensive, policy-gated)
   - Publishes to Kaggle Dataset via KagglePersistence
   - Cooldown minimum 5 minutes between normal publishes
   - Immediate on: significant change + cooldown, shutdown, explicit request

CheckpointManager decides WHETHER to publish.
KagglePersistence executes the publish.
Watchdog does NOT publish.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


MIN_PUBLISH_INTERVAL_SECONDS = 300  # 5 minutes


class PublishReason(str, Enum):
    NONE = "none"
    COOLDOWN_AND_CHANGES = "cooldown_and_changes"
    SHUTDOWN = "shutdown"
    EXPLICIT = "explicit"
    RECOVERY = "recovery"


@dataclass
class CheckpointPolicy:
    min_publish_interval: int = MIN_PUBLISH_INTERVAL_SECONDS
    always_on_shutdown: bool = True
    always_on_explicit: bool = True
    always_on_recovery: bool = False  # recovery is download, not publish by default


@dataclass
class CheckpointState:
    last_local_checkpoint: float = 0.0
    last_remote_publish: float = 0.0
    remote_publish_count: int = 0
    pending_significant_changes: int = 0
    remote_pending: bool = False


class CheckpointManager:
    """Decides when to perform local checkpoints and remote publishes."""

    def __init__(self, policy: Optional[CheckpointPolicy] = None):
        self.policy = policy or CheckpointPolicy()
        self.state = CheckpointState()

    def record_local_checkpoint(self) -> None:
        """Mark that a local checkpoint was taken."""
        self.state.last_local_checkpoint = time.time()

    def mark_significant_change(self) -> None:
        """Mark that significant work happened; remote publish may be warranted."""
        self.state.pending_significant_changes += 1
        self.state.remote_pending = True

    def should_publish_remote(
        self,
        *,
        reason: Optional[PublishReason] = None,
        significant_changes: Optional[int] = None,
    ) -> tuple[bool, PublishReason]:
        """Decide whether a remote publish should happen now.

        Returns (should_publish, reason).
        """
        now = time.time()
        changes = (
            significant_changes
            if significant_changes is not None
            else self.state.pending_significant_changes
        )

        if reason == PublishReason.EXPLICIT and self.policy.always_on_explicit:
            return True, PublishReason.EXPLICIT

        if reason == PublishReason.SHUTDOWN and self.policy.always_on_shutdown:
            return True, PublishReason.SHUTDOWN

        if reason == PublishReason.RECOVERY and self.policy.always_on_recovery:
            return True, PublishReason.RECOVERY

        elapsed = now - self.state.last_remote_publish
        if changes >= 1 and elapsed >= self.policy.min_publish_interval:
            return True, PublishReason.COOLDOWN_AND_CHANGES

        if self.state.remote_pending and elapsed >= self.policy.min_publish_interval:
            return True, PublishReason.COOLDOWN_AND_CHANGES

        return False, PublishReason.NONE

    def record_remote_publish(self) -> None:
        """Call after a successful remote publish."""
        self.state.last_remote_publish = time.time()
        self.state.remote_publish_count += 1
        self.state.pending_significant_changes = 0
        self.state.remote_pending = False

    def get_state(self) -> dict:
        return {
            "last_local_checkpoint": self.state.last_local_checkpoint,
            "last_remote_publish": self.state.last_remote_publish,
            "remote_publish_count": self.state.remote_publish_count,
            "pending_significant_changes": self.state.pending_significant_changes,
            "remote_pending": self.state.remote_pending,
            "min_publish_interval": self.policy.min_publish_interval,
        }
