"""Timing helpers.

Two clocks are used on purpose:

* ``time.perf_counter()`` -- monotonic, high-resolution. Used for every
  experimental duration (reaction time, movement time, ...). It is never
  affected by system clock adjustments.
* Wall-clock UTC timestamps (ISO 8601) -- used only to record *when* a session
  or trial happened, never to compute durations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Current wall-clock time as an ISO 8601 UTC string with microseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def monotonic_ms() -> float:
    """Monotonic high-resolution time in milliseconds."""
    return time.perf_counter() * 1000.0


@dataclass
class Stopwatch:
    """Monotonic stopwatch measuring elapsed milliseconds."""

    _start_ms: float | None = field(default=None, init=False)
    _stop_ms: float | None = field(default=None, init=False)

    def start(self) -> None:
        self._start_ms = monotonic_ms()
        self._stop_ms = None

    def stop(self) -> float:
        if self._start_ms is None:
            raise RuntimeError("Stopwatch.stop() called before start()")
        self._stop_ms = monotonic_ms()
        return self.elapsed_ms

    @property
    def running(self) -> bool:
        return self._start_ms is not None and self._stop_ms is None

    @property
    def elapsed_ms(self) -> float:
        if self._start_ms is None:
            return 0.0
        end = self._stop_ms if self._stop_ms is not None else monotonic_ms()
        return end - self._start_ms
