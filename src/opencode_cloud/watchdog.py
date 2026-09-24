"""Watchdog for OpenCode Cloud Workstation.

The watchdog monitors the OpenCode process and restarts it if it crashes.
It also coordinates with the checkpoint manager to trigger checkpoints
according to policy.

Important distinction:
- Process crash -> watchdog restarts OpenCode automatically.
- Runtime death -> watchdog does NOT survive. Recovery requires bootstrap + restore.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class Watchdog:
    """Monitors an OpenCode process and restarts it on failure."""

    def __init__(
        self,
        check_interval: int = 60,
        restart_callback: Optional[Callable[[], None]] = None,
        checkpoint_callback: Optional[Callable[[], bool]] = None,
    ):
        self.check_interval = check_interval
        self.restart_callback = restart_callback
        self.checkpoint_callback = checkpoint_callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._process_poll: Optional[Callable[[], Optional[int]]] = None

    def set_process_poll(self, poll_fn: Callable[[], Optional[int]]) -> None:
        """Set a function that returns None if process is alive, or exit code otherwise."""
        self._process_poll = poll_fn

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while self._running:
            try:
                time.sleep(self.check_interval)
                if self._process_poll:
                    if self._process_poll() is not None:
                        # Process died
                        if self.restart_callback:
                            self.restart_callback()
                if self.checkpoint_callback:
                    try:
                        self.checkpoint_callback()
                    except Exception:
                        pass
            except Exception:
                # Watchdog must never die silently
                pass

    @staticmethod
    def make_restart_action(proc_obj, restart_fn: Callable[[], None]) -> Callable[[], None]:
        """Helper to create a restart action that updates external references."""
        def action():
            try:
                if proc_obj.poll() is not None:
                    restart_fn()
            except Exception:
                pass

        return action