"""Tracking task: seeded target path, raw recording and time-weighted measures.

Trial sequence
    1. Start marker at the arena centre; click, stabilisation and foreperiod
       as described in ``app.experiment.timing``.
    2. The target appears at the arena centre (where the start marker was).
       t = 0 is taken as in Flick Aim (after the first paint containing the
       target; 50 ms fallback marks the trial ``timing_fallback``).
    3. The target moves along the trial's path for ``trial_duration_ms``.
       The participant keeps the crosshair on it; clicking is not required
       (clicks are stored as events but do not affect the measures).
    4. The trial ends at t = trial_duration_ms (``trial_end`` event).

Path
    Per axis: p(t) = centre + (A / 2) * sum_i w_i * (sin(2*pi*f_i*t + phi_i) - sin(phi_i)),
    with sum_i w_i = 1, so p(0) = centre and |p(t) - centre| <= A. Phases are
    drawn from the seed; A is reduced if the arena is too small (the amplitude
    actually used is stored in the plan).

Samples
    A sample (crosshair and target position at that instant) is stored for
    every mouse-move event and every ``sample_interval_ms`` timer tick, plus
    one at t = 0 and one at the end. The target position is computed from the
    path at the sample time.

Measures (time-weighted: each sample's state holds until the next sample)
    on_target_ratio    share of time with distance <= target radius
    mean_distance      mean crosshair-to-target distance (stored as error_distance)
    rms_distance       root-mean-square distance
    reaction_time_ms   t = 0 -> first sample >= movement_onset_threshold_px from the stable
                       pre-target position (t0 position for trials without a ``stable`` event)
    movement_distance  crosshair path length
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any

from app.data.models import TrialEvent, TrialResult, TrialSample
from app.experiment.common import CommonTaskParams, EventType, check, read_field
from app.experiment.pointing import movement_reference, relative_raw
from app.experiment.timing import timing_definition
from app.utils.validators import ValidationError

TIMING_DEFINITION: dict[str, str] = timing_definition(
    "tracking-timing-2",
    completion_time="not used; the trial lasts trial_duration_ms",
    trial_end="t0 + trial_duration_ms",
    aggregation="time-weighted; each sample holds until the next sample",
    on_target="distance(crosshair centre, target centre) <= target radius",
    coordinates="arena device pixels, origin top-left; crosshair = rendered centre",
)

MIN_AMPLITUDE_PX = 40


@dataclass(frozen=True)
class TrackingConfig:
    confirmed: bool
    trial_count: int
    start_marker_diameter_px: int
    start_marker_color: str
    foreperiod_ms: tuple[int, int]
    movement_onset_threshold_px: float
    random_seed: int
    stabilization_radius_px: float
    stabilization_movement_threshold_px: float
    stabilization_duration_ms: int
    trial_duration_ms: int
    target_diameter_px: int
    target_color: str
    sample_interval_ms: int
    path_amplitude_px: tuple[float, float]
    path_frequencies_hz: tuple[tuple[float, ...], tuple[float, ...]]
    path_component_weights: tuple[float, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackingConfig:
        task = "tracking_task"
        common = CommonTaskParams.parse(task, data)
        config = cls(
            **asdict(common),
            trial_duration_ms=read_field(task, data, "trial_duration_ms", int),
            target_diameter_px=read_field(task, data, "target_diameter_px", int),
            target_color=read_field(task, data, "target_color", str),
            sample_interval_ms=read_field(task, data, "sample_interval_ms", int),
            path_amplitude_px=read_field(task, data, "path_amplitude_px",
                                         lambda v: (float(v[0]), float(v[1]))),
            path_frequencies_hz=read_field(task, data, "path_frequencies_hz",
                                           lambda v: (tuple(map(float, v[0])), tuple(map(float, v[1])))),
            path_component_weights=read_field(task, data, "path_component_weights",
                                              lambda v: tuple(map(float, v))),
        )
        problems = []
        if config.trial_duration_ms <= 0:
            problems.append("trial_duration_ms must be > 0")
        if config.target_diameter_px < 2:
            problems.append("target_diameter_px must be >= 2")
        if not 1 <= config.sample_interval_ms <= 100:
            problems.append("sample_interval_ms must be 1..100")
        if min(config.path_amplitude_px) <= 0:
            problems.append("path_amplitude_px must be positive")
        weights = config.path_component_weights
        if not weights or min(weights) < 0 or not math.isclose(sum(weights), 1.0, abs_tol=1e-6):
            problems.append("path_component_weights must be non-negative and sum to 1")
        for axis in config.path_frequencies_hz:
            if len(axis) != len(weights) or min(axis, default=0) <= 0:
                problems.append("path_frequencies_hz needs one positive frequency per weight for x and y")
                break
        check(task, problems)
        return config

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["foreperiod_ms"] = list(self.foreperiod_ms)
        data["path_amplitude_px"] = list(self.path_amplitude_px)
        data["path_frequencies_hz"] = [list(a) for a in self.path_frequencies_hz]
        data["path_component_weights"] = list(self.path_component_weights)
        return data


@dataclass(frozen=True)
class TrackingPath:
    index: int
    center_x: float
    center_y: float
    amplitude_x: float
    amplitude_y: float
    frequencies_x: tuple[float, ...]
    frequencies_y: tuple[float, ...]
    phases_x: tuple[float, ...]
    phases_y: tuple[float, ...]
    weights: tuple[float, ...]
    foreperiod_ms: int

    @property
    def target_id(self) -> str:
        return f"tracking-{self.index + 1}"

    def _axis(self, t_s: float, center: float, amp: float, freqs, phases) -> float:
        return center + amp / 2 * sum(
            w * (math.sin(2 * math.pi * f * t_s + p) - math.sin(p))
            for w, f, p in zip(self.weights, freqs, phases)
        )

    def position(self, t_ms: float) -> tuple[float, float]:
        t_s = max(t_ms, 0.0) / 1000.0
        return (
            self._axis(t_s, self.center_x, self.amplitude_x, self.frequencies_x, self.phases_x),
            self._axis(t_s, self.center_y, self.amplitude_y, self.frequencies_y, self.phases_y),
        )

    def mean_speed(self, duration_ms: float, step_ms: float = 5.0) -> float:
        """Mean target speed in px/s over [0, duration_ms] (numerical path length / time)."""
        steps = max(1, int(duration_ms / step_ms))
        points = [self.position(duration_ms * i / steps) for i in range(steps + 1)]
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
        return length / (duration_ms / 1000.0)


def generate_tracking_plan(config: TrackingConfig, arena_w: int, arena_h: int, seed: int) -> list[TrackingPath]:
    rng = random.Random(seed)
    margin = config.target_diameter_px / 2 + 2
    amp_x = min(config.path_amplitude_px[0], arena_w / 2 - margin)
    amp_y = min(config.path_amplitude_px[1], arena_h / 2 - margin)
    if min(amp_x, amp_y) < MIN_AMPLITUDE_PX:
        raise ValidationError(f"Arena {arena_w}x{arena_h} px is too small for the tracking path")
    n = len(config.path_component_weights)
    low, high = config.foreperiod_ms
    return [
        TrackingPath(
            index=index, center_x=arena_w / 2, center_y=arena_h / 2,
            amplitude_x=amp_x, amplitude_y=amp_y,
            frequencies_x=config.path_frequencies_hz[0], frequencies_y=config.path_frequencies_hz[1],
            phases_x=tuple(round(rng.uniform(0, 2 * math.pi), 6) for _ in range(n)),
            phases_y=tuple(round(rng.uniform(0, 2 * math.pi), 6) for _ in range(n)),
            weights=config.path_component_weights,
            foreperiod_ms=rng.randint(low, high),
        )
        for index in range(config.trial_count)
    ]


@dataclass
class TrackingMeasures:
    result: TrialResult
    initial_x: float | None
    initial_y: float | None
    duration_ms: float | None
    on_target_ratio: float | None
    mean_distance: float | None
    rms_distance: float | None
    reaction_time_ms: float | None
    movement_distance: float | None


def compute_tracking_measures(
    samples: list[TrialSample],
    events: list[TrialEvent],
    target_diameter_px: float,
    movement_onset_threshold_px: float,
) -> TrackingMeasures:
    onset = next((e for e in events if e.event_type == EventType.TARGET_ONSET), None)
    end = next((e for e in events if e.event_type == EventType.TRIAL_END), None)
    window = [s for s in samples if onset and end and 0 <= s.t_ms <= end.t_ms and s.target_x is not None]
    if onset is None or end is None or len(window) < 2:
        return TrackingMeasures(TrialResult.INCOMPLETE, *([None] * 8))

    radius = target_diameter_px / 2
    total = on = weighted = weighted_sq = 0.0
    for a, b in zip(window, window[1:]):
        dt = b.t_ms - a.t_ms
        d = math.hypot(a.cursor_x - a.target_x, a.cursor_y - a.target_y)
        total += dt
        on += dt if d <= radius else 0.0
        weighted += dt * d
        weighted_sq += dt * d * d
    if total <= 0:
        return TrackingMeasures(TrialResult.INCOMPLETE, *([None] * 8))

    x0, y0 = onset.x, onset.y
    rx, ry = movement_reference(events, onset)
    moved = next(
        (s for s in window if math.hypot(s.cursor_x - rx, s.cursor_y - ry) >= movement_onset_threshold_px),
        None,
    )
    path = sum(
        math.hypot(b.cursor_x - a.cursor_x, b.cursor_y - a.cursor_y) for a, b in zip(window, window[1:])
    )
    return TrackingMeasures(
        result=TrialResult.TRACKED,
        initial_x=x0,
        initial_y=y0,
        duration_ms=end.t_ms,
        on_target_ratio=on / total,
        mean_distance=weighted / total,
        rms_distance=math.sqrt(weighted_sq / total),
        reaction_time_ms=moved.t_ms if moved else None,
        movement_distance=path,
    )


class TrackingRecorder:
    """Collects raw input for one tracking trial using absolute perf_counter seconds."""

    def __init__(self, path: TrackingPath, config: TrackingConfig) -> None:
        self.path = path
        self.config = config
        self._samples: list[tuple[float, float, float]] = []
        self._events: list[tuple[float, str, float, float]] = []
        self.t0: float | None = None
        self.ended = False

    def start_click(self, t: float, x: float, y: float) -> None:
        self._events.append((t, EventType.START_CLICK, x, y))

    def record_event(self, t: float, kind: str, x: float, y: float) -> None:
        self._events.append((t, kind, x, y))

    def raw_without_onset(self, t_ref: float) -> tuple[list[TrialSample], list[TrialEvent]]:
        return relative_raw(self._samples, self._events, t_ref)

    def sample(self, t: float, x: float, y: float) -> None:
        if not self.ended:
            self._samples.append((t, x, y))

    def target_shown(self, t: float, x: float, y: float) -> None:
        self.t0 = t
        self._events.append((t, EventType.TARGET_ONSET, x, y))
        self._samples.append((t, x, y))

    def click(self, t: float, x: float, y: float) -> None:
        if self.ended:
            return
        kind = EventType.CLICK if self.t0 is not None and t >= self.t0 else EventType.EARLY_CLICK
        self._events.append((t, kind, x, y))

    def end(self, t: float, x: float, y: float) -> None:
        if not self.ended:
            self._samples.append((t, x, y))
            self._events.append((t, EventType.TRIAL_END, x, y))
            self.ended = True

    def elapsed_ms(self, t: float) -> float:
        return (t - self.t0) * 1000.0 if self.t0 is not None else 0.0

    @property
    def early_clicks(self) -> int:
        return sum(1 for e in self._events if e[1] == EventType.EARLY_CLICK)

    def raw(self) -> tuple[list[TrialSample], list[TrialEvent]]:
        if self.t0 is None:
            raise RuntimeError("target was never shown")
        radius = self.config.target_diameter_px / 2
        samples = []
        for t, x, y in self._samples:
            t_ms = (t - self.t0) * 1000.0
            if t_ms >= 0:
                tx, ty = self.path.position(t_ms)
                samples.append(TrialSample(t_ms, x, y, tx, ty, math.hypot(x - tx, y - ty) <= radius))
            else:
                samples.append(TrialSample(t_ms, x, y))
        events = []
        for t, kind, x, y in self._events:
            t_ms = (t - self.t0) * 1000.0
            is_hit = None
            if kind == EventType.CLICK:
                tx, ty = self.path.position(t_ms)
                is_hit = math.hypot(x - tx, y - ty) <= radius
            events.append(TrialEvent(t_ms, kind, x, y, is_hit))
        return samples, events

    def measures(self) -> TrackingMeasures:
        samples, events = self.raw()
        return compute_tracking_measures(
            samples, events, self.config.target_diameter_px, self.config.movement_onset_threshold_px,
        )
