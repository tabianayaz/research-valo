"""Loader for versioned research parameters (``research_parameters.json``).

All values that could affect research validity live in that JSON file rather
than in code, so they can be changed (and recorded) without code edits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.validators import ValidationError

DEFAULT_RESEARCH_PARAMETERS_PATH = Path(__file__).with_name("research_parameters.json")


@dataclass(frozen=True)
class ResearchParameters:
    baseline_confirmed: bool
    baseline_crosshair: dict[str, Any]
    px_per_unit: float
    parameter_ranges: dict[str, tuple[float, float]]
    experiment_background_color: str
    source_path: Path
    flick_task: dict[str, Any]
    tracking_task: dict[str, Any]
    switching_task: dict[str, Any]
    recommendation: dict[str, Any]
    protocol: dict[str, Any]

    def task_parameters(self, experiment_type: str) -> dict[str, Any]:
        return {
            "flick": self.flick_task, "tracking": self.tracking_task, "switching": self.switching_task,
        }[str(experiment_type)]

    def as_dict(self) -> dict[str, Any]:
        """Snapshot suitable for storing alongside a session."""
        return {
            "baseline_confirmed": self.baseline_confirmed,
            "baseline_crosshair": dict(self.baseline_crosshair),
            "px_per_unit": self.px_per_unit,
            "parameter_ranges": {k: list(v) for k, v in self.parameter_ranges.items()},
            "experiment_background_color": self.experiment_background_color,
            "flick_task": dict(self.flick_task),
            "tracking_task": dict(self.tracking_task),
            "switching_task": dict(self.switching_task),
            "recommendation": dict(self.recommendation),
            "protocol": dict(self.protocol),
        }


def _task(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Task parameters without ``_comment``-style keys."""
    return {k: v for k, v in data[key].items() if not k.startswith("_")}


def load_research_parameters(path: Path | None = None) -> ResearchParameters:
    resolved = path or DEFAULT_RESEARCH_PARAMETERS_PATH
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
        ranges = {
            name: (float(bounds[0]), float(bounds[1]))
            for name, bounds in data["crosshair_parameter_ranges"].items()
        }
        params = ResearchParameters(
            baseline_confirmed=bool(data["baseline_confirmed"]),
            baseline_crosshair=dict(data["baseline_crosshair"]),
            px_per_unit=float(data["crosshair_units"]["px_per_unit"]),
            parameter_ranges=ranges,
            experiment_background_color=str(data["experiment_background_color"]),
            source_path=resolved,
            flick_task=_task(data, "flick_task"),
            tracking_task=_task(data, "tracking_task"),
            switching_task=_task(data, "switching_task"),
            recommendation=_task(data, "recommendation"),
            protocol=_task(data, "protocol"),
        )
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise ValidationError(f"Invalid research parameter file {resolved}: {exc}") from exc
    if params.px_per_unit <= 0:
        raise ValidationError("crosshair_units.px_per_unit must be greater than 0")
    for name, (low, high) in ranges.items():
        if low > high:
            raise ValidationError(f"Range for {name} is inverted: {low} > {high}")
    return params
