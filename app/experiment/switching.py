"""Target Switching task: target sequences and per-target segments.

Trial sequence
    1. Start marker at the arena centre; click, stabilisation and foreperiod
       as described in ``app.experiment.timing``.
    2. All targets of the trial appear at once. The active target is drawn in
       the target colour, the others in the inactive colour. t = 0 of the
       first segment is taken as in Flick Aim (after the first paint).
    3. One click per target: the first left click ends the active segment
       (hit if within the active target's radius, otherwise miss) and the next
       target becomes active immediately. The next segment's t = 0 is that
       click's timestamp. If no click occurs within ``timeout_ms`` the segment
       ends with ``timeout`` and the next target becomes active.
    4. The trial ends after the last target.

Storage
    One ``trials`` row per segment (target). ``previous_target_id`` links a
    segment to the target before it; segments with sequence_index >= 1 are
    switches, and their completion_time_ms is the switching time (previous
    click -> this click). Measures per segment are identical to Flick Aim
    (``app.experiment.pointing``).
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Any

from app.experiment.common import CommonTaskParams, check, read_field
from app.experiment.flick import allowed_angles, balanced, point_at
from app.experiment.timing import timing_definition
from app.utils.validators import ValidationError

TIMING_DEFINITION: dict[str, str] = timing_definition(
    "switching-timing-2",
    t0_first_segment="immediately after the first paint that contains the targets (stabilisation and "
                     "foreperiod rules apply only to the first segment)",
    t0_next_segment="timestamp of the click (or timeout) that ended the previous segment; movement onset "
                    "is measured from that click position (timing_quality previous_click)",
    switching_time="completion_time_ms of segments with sequence_index >= 1",
    segment_end="first left click at t >= 0, or timeout_ms after the segment's t0",
    hit="distance(crosshair centre, active target centre) <= target radius at the click",
    coordinates="arena device pixels, origin top-left; crosshair = rendered centre",
)


@dataclass(frozen=True)
class SwitchingConfig:
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
    targets_per_trial: int
    target_diameter_px: int
    first_distances_px: tuple[int, ...]
    switch_distances_px: tuple[int, ...]
    min_separation_px: int
    target_color: str
    inactive_target_color: str
    timeout_ms: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwitchingConfig:
        task = "switching_task"
        common = CommonTaskParams.parse(task, data)
        ints = lambda v: tuple(int(d) for d in v)  # noqa: E731
        config = cls(
            **asdict(common),
            targets_per_trial=read_field(task, data, "targets_per_trial", int),
            target_diameter_px=read_field(task, data, "target_diameter_px", int),
            first_distances_px=read_field(task, data, "first_distances_px", ints),
            switch_distances_px=read_field(task, data, "switch_distances_px", ints),
            min_separation_px=read_field(task, data, "min_separation_px", int),
            target_color=read_field(task, data, "target_color", str),
            inactive_target_color=read_field(task, data, "inactive_target_color", str),
            timeout_ms=read_field(task, data, "timeout_ms", int),
        )
        problems = []
        if config.targets_per_trial < 2:
            problems.append("targets_per_trial must be >= 2")
        if config.target_diameter_px < 2:
            problems.append("target_diameter_px must be >= 2")
        for name in ("first_distances_px", "switch_distances_px"):
            values = getattr(config, name)
            if not values or min(values) <= 0:
                problems.append(f"{name} must be positive")
        if config.min_separation_px < config.target_diameter_px:
            problems.append("min_separation_px must be >= target_diameter_px (targets must not overlap)")
        if config.timeout_ms <= 0:
            problems.append("timeout_ms must be > 0")
        check(task, problems)
        return config

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("foreperiod_ms", "first_distances_px", "switch_distances_px"):
            data[key] = list(data[key])
        return data


@dataclass(frozen=True)
class SwitchingTarget:
    trial_index: int
    sequence_index: int
    x: float
    y: float
    planned_distance_px: int
    angle_deg: float

    @property
    def target_id(self) -> str:
        return f"switch-{self.trial_index + 1}-{self.sequence_index + 1}"


@dataclass(frozen=True)
class SwitchingTrial:
    index: int
    targets: tuple[SwitchingTarget, ...]
    foreperiod_ms: int


def generate_switching_plan(config: SwitchingConfig, arena_w: int, arena_h: int, seed: int) -> list[SwitchingTrial]:
    """Seeded target sequences.

    First targets use ``first_distances_px`` from the centre; each following
    target uses ``switch_distances_px`` from the previous target. Both are
    balanced across the session and shuffled. Angles are drawn among
    whole-degree angles that keep the target inside the arena and at least
    ``min_separation_px`` from every other target in the trial and from the
    start marker.
    """
    rng = random.Random(seed)
    cx, cy = arena_w / 2, arena_h / 2
    margin = config.target_diameter_px / 2 + 2
    firsts = balanced(config.first_distances_px, config.trial_count, rng)
    switches = balanced(config.switch_distances_px, config.trial_count * (config.targets_per_trial - 1), rng)
    low, high = config.foreperiod_ms

    plan = []
    for trial_index in range(config.trial_count):
        targets: list[SwitchingTarget] = []
        origin = (cx, cy)
        for seq in range(config.targets_per_trial):
            distance = firsts[trial_index] if seq == 0 else switches.pop()
            placed = [(cx, cy)] + [(t.x, t.y) for t in targets]
            angles = [
                a for a in allowed_angles(origin[0], origin[1], distance, arena_w, arena_h, margin)
                if all(
                    math.dist(point_at(origin[0], origin[1], distance, a), p) >= config.min_separation_px
                    for p in placed
                )
            ]
            if not angles:
                raise ValidationError(
                    f"Arena {arena_w}x{arena_h} px is too small to place switching targets "
                    f"(distance {distance} px)"
                )
            angle = rng.choice(angles)
            x, y = point_at(origin[0], origin[1], distance, angle)
            targets.append(SwitchingTarget(trial_index, seq, x, y, distance, float(angle)))
            origin = (x, y)
        plan.append(SwitchingTrial(trial_index, tuple(targets), rng.randint(low, high)))
    return plan
