"""Raw recording and measures for one click-on-a-target segment.

Used by Flick Aim (one segment per trial) and Target Switching (one segment
per target in a sequence). See ``app.experiment.flick`` for the timing
definitions; they are identical for both tasks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.data.models import TrialEvent, TrialResult, TrialSample
from app.experiment.common import EventType


@dataclass
class PointingMeasures:
    result: TrialResult
    initial_x: float | None
    initial_y: float | None
    target_distance: float | None
    reaction_time_ms: float | None
    movement_time_ms: float | None
    completion_time_ms: float | None
    error_distance: float | None
    movement_distance: float | None
    final_distance: float | None


def movement_reference(events: list[TrialEvent], onset: TrialEvent) -> tuple[float, float]:
    """Position movement onset is measured from: the stable pre-target position, else the t0 position."""
    stable = next((e for e in events if e.event_type == EventType.STABLE and e.t_ms <= 0), None)
    return (stable.x, stable.y) if stable is not None else (onset.x, onset.y)


def relative_raw(
    samples: list[tuple[float, float, float]], events: list[tuple[float, str, float, float]], t_ref: float,
) -> tuple[list[TrialSample], list[TrialEvent]]:
    """Raw data of a trial that never showed a target, with times relative to ``t_ref``."""
    return (
        [TrialSample(t_ms=(t - t_ref) * 1000.0, cursor_x=x, cursor_y=y) for t, x, y in samples],
        [TrialEvent(t_ms=(t - t_ref) * 1000.0, event_type=kind, x=x, y=y) for t, kind, x, y in events],
    )


def compute_pointing_measures(
    samples: list[TrialSample],
    events: list[TrialEvent],
    target_x: float,
    target_y: float,
    target_diameter_px: float,
    movement_onset_threshold_px: float,
) -> PointingMeasures:
    """Derive segment measures from raw samples/events."""
    onset = next((e for e in events if e.event_type == EventType.TARGET_ONSET), None)
    end = next(
        (e for e in events if e.event_type in (EventType.CLICK, EventType.TIMEOUT) and e.t_ms >= 0),
        None,
    )
    if onset is None or end is None:
        return PointingMeasures(TrialResult.INCOMPLETE, *([None] * 9))

    x0, y0 = onset.x, onset.y
    rx, ry = movement_reference(events, onset)
    path = [(0.0, x0, y0)] + [
        (s.t_ms, s.cursor_x, s.cursor_y) for s in samples if 0 <= s.t_ms <= end.t_ms
    ] + [(end.t_ms, end.x, end.y)]
    movement_distance = sum(
        math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(path, path[1:])
    )
    onset_sample = next(
        (p for p in path[1:] if math.hypot(p[1] - rx, p[2] - ry) >= movement_onset_threshold_px),
        None,
    )
    reaction = onset_sample[0] if onset_sample else None
    final_distance = math.hypot(end.x - target_x, end.y - target_y)

    if end.event_type == EventType.TIMEOUT:
        result = TrialResult.TIMEOUT
        movement = completion = error = None
    else:
        result = TrialResult.HIT if final_distance <= target_diameter_px / 2 else TrialResult.MISS
        completion = end.t_ms
        movement = end.t_ms - reaction if reaction is not None else None
        error = final_distance
    return PointingMeasures(
        result=result,
        initial_x=x0,
        initial_y=y0,
        target_distance=math.hypot(target_x - x0, target_y - y0),
        reaction_time_ms=reaction,
        movement_time_ms=movement,
        completion_time_ms=completion,
        error_distance=error,
        movement_distance=movement_distance,
        final_distance=final_distance,
    )


class PointingRecorder:
    """Collects raw input for one segment using absolute perf_counter seconds."""

    def __init__(self, target_x: float, target_y: float, diameter_px: float, onset_threshold_px: float) -> None:
        self.target_x = target_x
        self.target_y = target_y
        self.diameter_px = diameter_px
        self.onset_threshold_px = onset_threshold_px
        self._samples: list[tuple[float, float, float]] = []
        self._events: list[tuple[float, str, float, float]] = []
        self.t0: float | None = None
        self.ended = False

    def start_click(self, t: float, x: float, y: float) -> None:
        self._events.append((t, EventType.START_CLICK, x, y))

    def record_event(self, t: float, kind: str, x: float, y: float) -> None:
        self._events.append((t, kind, x, y))

    def move(self, t: float, x: float, y: float) -> None:
        if not self.ended:
            self._samples.append((t, x, y))

    def raw_without_onset(self, t_ref: float) -> tuple[list[TrialSample], list[TrialEvent]]:
        return relative_raw(self._samples, self._events, t_ref)

    def target_shown(self, t: float, x: float, y: float) -> None:
        self.t0 = t
        self._events.append((t, EventType.TARGET_ONSET, x, y))

    def click(self, t: float, x: float, y: float) -> bool:
        """Record a left click. Returns True if it ended the segment."""
        if self.ended:
            return False
        if self.t0 is None or t < self.t0:
            self._events.append((t, EventType.EARLY_CLICK, x, y))
            return False
        self._events.append((t, EventType.CLICK, x, y))
        self.ended = True
        return True

    def timeout(self, t: float, x: float, y: float) -> None:
        if not self.ended:
            self._events.append((t, EventType.TIMEOUT, x, y))
            self.ended = True

    @property
    def early_clicks(self) -> int:
        return sum(1 for e in self._events if e[1] == EventType.EARLY_CLICK)

    def _is_on_target(self, x: float, y: float) -> bool:
        return math.hypot(x - self.target_x, y - self.target_y) <= self.diameter_px / 2

    def raw(self) -> tuple[list[TrialSample], list[TrialEvent]]:
        if self.t0 is None:
            raise RuntimeError("target was never shown")
        t0 = self.t0
        samples = []
        for t, x, y in self._samples:
            visible = t >= t0
            samples.append(TrialSample(
                t_ms=(t - t0) * 1000.0, cursor_x=x, cursor_y=y,
                target_x=self.target_x if visible else None,
                target_y=self.target_y if visible else None,
                on_target=self._is_on_target(x, y) if visible else None,
            ))
        events = [
            TrialEvent(
                t_ms=(t - t0) * 1000.0, event_type=kind, x=x, y=y,
                is_hit=self._is_on_target(x, y) if kind == EventType.CLICK else None,
            )
            for t, kind, x, y in self._events
        ]
        return samples, events

    def measures(self) -> PointingMeasures:
        samples, events = self.raw()
        return compute_pointing_measures(
            samples, events, self.target_x, self.target_y, self.diameter_px, self.onset_threshold_px,
        )
