"""Pieces shared by all aim tasks: event names and common parameter parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.validators import ValidationError


class EventType:
    START_CLICK = "start_click"
    EARLY_CLICK = "early_click"
    TARGET_ONSET = "target_onset"
    CLICK = "click"
    TIMEOUT = "timeout"
    TRIAL_END = "trial_end"
    STABILIZATION_RESET = "stabilization_reset"
    STABLE = "stable"
    PRE_TARGET_MOVEMENT = "pre_target_movement"


@dataclass(frozen=True)
class CommonTaskParams:
    """Parameters every task uses for its start-marker / stabilisation / foreperiod procedure.

    See ``app.experiment.timing`` for how they are used.
    """

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

    @classmethod
    def parse(cls, task: str, data: dict[str, Any]) -> CommonTaskParams:
        try:
            params = cls(
                confirmed=bool(data["confirmed"]),
                trial_count=int(data["trial_count"]),
                start_marker_diameter_px=int(data["start_marker_diameter_px"]),
                start_marker_color=str(data["start_marker_color"]),
                foreperiod_ms=(int(data["foreperiod_ms"][0]), int(data["foreperiod_ms"][1])),
                movement_onset_threshold_px=float(data["movement_onset_threshold_px"]),
                random_seed=int(data["random_seed"]),
                stabilization_radius_px=float(data["stabilization_radius_px"]),
                stabilization_movement_threshold_px=float(data["stabilization_movement_threshold_px"]),
                stabilization_duration_ms=int(data["stabilization_duration_ms"]),
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ValidationError(f"Invalid {task} parameters: {exc}") from exc
        problems = []
        if params.trial_count < 1:
            problems.append("trial_count must be >= 1")
        if params.start_marker_diameter_px < 2:
            problems.append("start_marker_diameter_px must be >= 2")
        low, high = params.foreperiod_ms
        if low < 0 or high < low:
            problems.append("foreperiod_ms must be [low, high] with 0 <= low <= high")
        if params.movement_onset_threshold_px <= 0:
            problems.append("movement_onset_threshold_px must be > 0")
        if params.stabilization_radius_px < params.start_marker_diameter_px / 2:
            problems.append("stabilization_radius_px must be >= the start marker radius")
        if params.stabilization_movement_threshold_px <= 0:
            problems.append("stabilization_movement_threshold_px must be > 0")
        if params.stabilization_duration_ms < 0:
            problems.append("stabilization_duration_ms must be >= 0")
        if problems:
            raise ValidationError(f"Invalid {task} parameters: " + "; ".join(problems))
        return params


def read_field(task: str, data: dict[str, Any], key: str, convert):
    try:
        return convert(data[key])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValidationError(f"Invalid {task} parameters: {key}: {exc}") from exc


def check(task: str, problems: list[str]) -> None:
    if problems:
        raise ValidationError(f"Invalid {task} parameters: " + "; ".join(problems))
