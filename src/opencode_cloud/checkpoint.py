"""Checkpoint strategy for OpenCode Cloud Workstation.

Two levels:

1. Local checkpoint (cheap, frequent)
   - Saved under /kaggle/working/opencode_cloud/
   - Does NOT create a Dataset version

2. Remote checkpoint (expensive, policy-gated)
   - Publishes to Kaggle Dataset via KagglePersistence ONLY
   - Cooldown minimum 5 minutes between normal publishes
   - Immediate on: significant change + cooldown, shutdown, explicit request
   - NEVER triggers GitHub sync (GitHub is separate versioning)

Significant change detection
----------------------------
A "significant change" is detected by comparing a workspace fingerprint
(file count + total size + sample of relative paths/mtimes) against the
last recorded fingerprint.

What counts as significant:
- New, deleted, or renamed files under workspace/
- Content growth beyond a small threshold (default: any size delta)

What does NOT force publish by itself:
- Unchanged workspace (fingerprint match)
- Watchdog process restarts
- Mere passage of time without changes

CheckpointManager decides WHETHER to publish.
KagglePersistence executes the publish.
Watchdog does NOT publish.
GitHubSync is NOT invoked from checkpoint paths.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
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
    last_workspace_fingerprint: str = ""


def workspace_fingerprint(workspace: Path, *, max_files: int = 500) -> str:
    """Compute a stable fingerprint of workspace content.

    Uses relative path, size, and mtime for up to max_files entries.
    Deterministic and cheap — no full file hashing of large blobs.
    """
    workspace = Path(workspace)
    if not workspace.exists():
        return "empty"
    entries: list[str] = []
    try:
        for p in sorted(workspace.rglob("*")):
            if not p.is_file():
                continue
            try:
                st = p.stat()
                rel = p.relative_to(workspace).as_posix()
                entries.append(f"{rel}:{st.st_size}:{int(st.st_mtime)}")
            except OSError:
                continue
            if len(entries) >= max_files:
                break
    except OSError:
        return "unreadable"
    raw = "\n".join(entries).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


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

    def observe_workspace(self, workspace: Path) -> bool:
        """Compare workspace fingerprint to last known.

        Returns True if a significant change was detected and recorded.
        Call this before deciding on remote publish for COOLDOWN_AND_CHANGES.
        """
        fp = workspace_fingerprint(workspace)
        if not self.state.last_workspace_fingerprint:
            # First observation — establish baseline, not a "change"
            self.state.last_workspace_fingerprint = fp
            return False
        if fp != self.state.last_workspace_fingerprint:
            self.state.last_workspace_fingerprint = fp
            self.mark_significant_change()
            return True
        return False

    def set_baseline_fingerprint(self, workspace: Path) -> str:
        """Set fingerprint baseline without counting as a change."""
        fp = workspace_fingerprint(workspace)
        self.state.last_workspace_fingerprint = fp
        return fp

    def should_publish_remote(
        self,
        *,
        reason: Optional[PublishReason] = None,
        significant_changes: Optional[int] = None,
        now: Optional[float] = None,
    ) -> tuple[bool, PublishReason]:
        """Decide whether a remote publish should happen now.

        Returns (should_publish, reason).

        EXPLICIT and SHUTDOWN bypass cooldown.
        COOLDOWN_AND_CHANGES requires pending changes AND elapsed >= interval.
        """
        clock = now if now is not None else time.time()
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

        elapsed = clock - self.state.last_remote_publish
        if changes >= 1 and elapsed >= self.policy.min_publish_interval:
            return True, PublishReason.COOLDOWN_AND_CHANGES

        if self.state.remote_pending and elapsed >= self.policy.min_publish_interval:
            return True, PublishReason.COOLDOWN_AND_CHANGES

        return False, PublishReason.NONE

    def record_remote_publish(self, *, now: Optional[float] = None) -> None:
        """Call after a successful remote publish."""
        clock = now if now is not None else time.time()
        self.state.last_remote_publish = clock
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
            "last_workspace_fingerprint": self.state.last_workspace_fingerprint[:16]
            if self.state.last_workspace_fingerprint
            else "",
        }
