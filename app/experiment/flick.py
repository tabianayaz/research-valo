"""Flick Aim task: configuration, target plan and per-trial measures.

Coordinate space (all tasks)
    Arena device (physical) pixels, origin at the arena's top-left corner. The
    crosshair position is the rendered crosshair centre, i.e. the mouse
    position converted to device pixels and rounded to the pixel boundary the
    crosshair is drawn on.

Trial sequence (common procedure and timing: ``app.experiment.timing``)
    1. A start marker is shown at the arena centre.
    2. The participant clicks the start marker -> ``start_click`` event, then
       holds the cursor still (stabilisation) -> ``stable`` event, then the
       foreperiod (seeded random duration) runs. Movement during the
       foreperiod invalidates the trial (``invalid_pre_movement``).
    3. After the foreperiod the target is drawn. t = 0 is ``perf_counter()``
       taken immediately after the first paint that contains the target
       (``target_onset`` event). Display/compositor latency is not measured.
       If the window receives no paint within 50 ms (e.g. it is obscured),
       t = 0 is taken then and the trial is marked ``timing_fallback``.
    4. The first left click at t >= 0 ends the trial (``click`` event).
       Clicks before t = 0 are stored as ``early_click`` and do not end it.
    5. If no click occurs within ``timeout_ms`` after t = 0 the trial ends
       with a ``timeout`` event.

Times are milliseconds relative to t = 0 (negative before target onset),
measured with ``time.perf_counter()`` when Qt delivers the input event.

Measures (all recomputable from the stored samples and events)
    reaction_time_ms   t = 0 -> first sample whose distance from the stable
                       pre-target position is >= movement_onset_threshold_px
    movement_time_ms   movement onset -> ending click
    completion_time_ms t = 0 -> ending click (None for timeouts)
    error_distance     crosshair-to-target-centre distance at the click
    movement_distance  crosshair path length from t = 0 to the end of the trial
    target_distance    crosshair position at t = 0 -> target centre
    hit                click with error_distance <= target radius
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any

from app.experiment.common import CommonTaskParams, EventType, check, read_field
from app.experiment.pointing import PointingMeasures, PointingRecorder, compute_pointing_measures
from app.experiment.timing import timing_definition
from app.utils.validators import ValidationError

TIMING_DEFINITION_VERSION = "flick-timing-2"

TIMING_DEFINITION: dict[str, str] = timing_definition(
    TIMING_DEFINITION_VERSION,
    completion_time="t0 -> ending click; null for timeout",
    trial_end="first left click at t >= 0, or timeout_ms after t0",
    hit="distance(crosshair centre, target centre) <= target radius at the click",
    coordinates="arena device pixels, origin top-left; crosshair = rendered centre",
)

FlickMeasures = PointingMeasures
compute_flick_measures = compute_pointing_measures

__all__ = [
    "EventType", "FlickConfig", "FlickMeasures", "FlickTarget", "FlickTrialRecorder",
    "TIMING_DEFINITION", "allowed_angles", "compute_flick_measures", "generate_plan",
]


@dataclass(frozen=True)
class FlickConfig:
    confirmed: bool
    trial_count: int
    target_diameter_px: int
    target_distances_px: tuple[int, ...]
    target_color: str
    start_marker_diameter_px: int
    start_marker_color: str
    foreperiod_ms: tuple[int, int]
    timeout_ms: int
    movement_onset_threshold_px: float
    random_seed: int
    stabilization_radius_px: float
    stabilization_movement_threshold_px: float
    stabilization_duration_ms: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlickConfig:
        task = "flick_task"
        common = CommonTaskParams.parse(task, data)
        config = cls(
            target_diameter_px=read_field(task, data, "target_diameter_px", int),
            target_distances_px=read_field(task, data, "target_distances_px",
                                           lambda v: tuple(int(d) for d in v)),
            target_color=read_field(task, data, "target_color", str),
            timeout_ms=read_field(task, data, "timeout_ms", int),
            **asdict(common),
        )
        problems = []
        if config.target_diameter_px < 2:
            problems.append("target_diameter_px must be >= 2")
        if not config.target_distances_px or min(config.target_distances_px) <= 0:
            problems.append("target_distances_px must be positive")
        if config.timeout_ms <= 0:
            problems.append("timeout_ms must be > 0")
        check(task, problems)
        return config

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["target_distances_px"] = list(self.target_distances_px)
        data["foreperiod_ms"] = list(self.foreperiod_ms)
        return data


@dataclass(frozen=True)
class FlickTarget:
    index: int
    x: float
    y: float
    planned_distance_px: int
    angle_deg: float
    foreperiod_ms: int

    @property
    def target_id(self) -> str:
        return f"flick-{self.index + 1}"


def allowed_angles(
    origin_x: float, origin_y: float, distance: float, arena_w: int, arena_h: int, margin: float,
) -> list[int]:
    """Whole-degree angles (0 = right, counter-clockwise) that keep a point inside the margins."""
    return [
        a for a in range(360)
        if margin <= origin_x + distance * math.cos(math.radians(a)) <= arena_w - margin
        and margin <= origin_y - distance * math.sin(math.radians(a)) <= arena_h - margin
    ]


def point_at(origin_x: float, origin_y: float, distance: float, angle_deg: float) -> tuple[float, float]:
    return (
        round(origin_x + distance * math.cos(math.radians(angle_deg)), 3),
        round(origin_y - distance * math.sin(math.radians(angle_deg)), 3),
    )


def balanced(values: tuple[int, ...], count: int, rng: random.Random) -> list[int]:
    """Each value equally often (remainder spread over the first values), shuffled."""
    items = [values[i % len(values)] for i in range(count)]
    rng.shuffle(items)
    return items


def generate_plan(config: FlickConfig, arena_w: int, arena_h: int, seed: int) -> list[FlickTarget]:
    """Seeded target sequence measured from the arena centre.

    Each distance occurs equally often, order is shuffled, and the angle is
    drawn uniformly among the whole-degree angles that keep the whole target
    inside the arena. The same seed and arena size always give the same plan;
    a different arena size can change the angles because fewer angles may fit.
    """
    rng = random.Random(seed)
    cx, cy = arena_w / 2, arena_h / 2
    margin = config.target_diameter_px / 2 + 2
    plan = []
    for index, distance in enumerate(balanced(config.target_distances_px, config.trial_count, rng)):
        angles = allowed_angles(cx, cy, distance, arena_w, arena_h, margin)
        if not angles:
            raise ValidationError(
                f"Arena {arena_w}x{arena_h} px is too small for a target distance of {distance} px"
            )
        angle = rng.choice(angles)
        x, y = point_at(cx, cy, distance, angle)
        low, high = config.foreperiod_ms
        plan.append(FlickTarget(
            index=index, x=x, y=y, planned_distance_px=distance,
            angle_deg=float(angle), foreperiod_ms=rng.randint(low, high),
        ))
    return plan


class FlickTrialRecorder(PointingRecorder):
    def __init__(self, target: FlickTarget, config: FlickConfig) -> None:
        super().__init__(target.x, target.y, config.target_diameter_px, config.movement_onset_threshold_px)
        self.target = target
        self.config = config
