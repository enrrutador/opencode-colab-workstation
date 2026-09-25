"""Watchdog for OpenCode process only.

Responsibility:
  - Monitor the OpenCode process
  - If it dies: detect, call a REAL restart function, log the result

Does NOT:
  - Publish Kaggle Dataset
  - Git push
  - Act as the persistence system
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional


class Watchdog:
    """Monitors an OpenCode process and restarts it on failure."""

    def __init__(
        self,
        check_interval: int = 30,
        restart_fn: Optional[Callable[[], object]] = None,
        process_poll: Optional[Callable[[], Optional[int]]] = None,
    ):
        """
        Args:
            check_interval: Seconds between checks.
            restart_fn: Callable that starts a new OpenCode process and returns
                        something with a .poll() method (e.g. subprocess.Popen).
                        MUST be a real restart, not a no-op.
            process_poll: Callable returning None if alive, or exit code if dead.
                          If not set, uses the last process returned by restart_fn.
        """
        self.check_interval = check_interval
        self.restart_fn = restart_fn
        self._process_poll = process_poll
        self._process: Optional[object] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.restart_count = 0
        self.last_restart_ok: Optional[bool] = None
        self.last_error: Optional[str] = None

    def set_process(self, proc: object) -> None:
        """Set the process object currently being watched (must have .poll())."""
        self._process = proc

    def set_restart_fn(self, fn: Callable[[], object]) -> None:
        self.restart_fn = fn

    def start(self) -> None:
        if self._running:
            return
        if self.restart_fn is None:
            raise RuntimeError(
                "Watchdog requires a real restart_fn; cannot start with no-op"
            )
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _is_dead(self) -> bool:
        if self._process_poll is not None:
            return self._process_poll() is not None
        if self._process is None:
            return True
        poll = getattr(self._process, "poll", None)
        if poll is None:
            return True
        return poll() is not None

    def _loop(self) -> None:
        while self._running:
            try:
                time.sleep(self.check_interval)
                if not self._running:
                    break
                if self._is_dead():
                    self._do_restart()
            except Exception as e:
                self.last_error = repr(e)

    def _do_restart(self) -> None:
        if self.restart_fn is None:
            self.last_restart_ok = False
            self.last_error = "no restart_fn"
            return
        try:
            new_proc = self.restart_fn()
            self._process = new_proc
            self.restart_count += 1
            self.last_restart_ok = True
            self.last_error = None
        except Exception as e:
            self.last_restart_ok = False
            self.last_error = repr(e)

    def status(self) -> dict:
        return {
            "running": self._running,
            "restart_count": self.restart_count,
            "last_restart_ok": self.last_restart_ok,
            "last_error": self.last_error,
            "process_dead": self._is_dead() if self._process or self._process_poll else None,
        }
