"""Deterministic task-order groups used by controlled assessments.

The six groups are the six permutations of Flick Aim (F), Tracking (T) and
Target Switching (S). Participants are assigned in creation sequence modulo
six. The assignment is then stored on the participant and is immutable; it is
never recomputed between sessions.

This is an implementation/allocation method, not a claim that the method is
scientifically superior. The final allocation strategy remains a research
decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.data.models import ExperimentType
from app.utils.validators import ValidationError

TASK_ORDER_METHOD = "counterbalanced"
ASSIGNMENT_METHOD = "participant_sequence_modulo_6"

TASK_ORDER_GROUPS: dict[str, tuple[ExperimentType, ...]] = {
    "FTS": (ExperimentType.FLICK, ExperimentType.TRACKING, ExperimentType.SWITCHING),
    "FST": (ExperimentType.FLICK, ExperimentType.SWITCHING, ExperimentType.TRACKING),
    "TFS": (ExperimentType.TRACKING, ExperimentType.FLICK, ExperimentType.SWITCHING),
    "TSF": (ExperimentType.TRACKING, ExperimentType.SWITCHING, ExperimentType.FLICK),
    "SFT": (ExperimentType.SWITCHING, ExperimentType.FLICK, ExperimentType.TRACKING),
    "STF": (ExperimentType.SWITCHING, ExperimentType.TRACKING, ExperimentType.FLICK),
}
TASK_LABELS = {
    ExperimentType.FLICK: "Flick Aim",
    ExperimentType.TRACKING: "Tracking",
    ExperimentType.SWITCHING: "Target Switching",
}


@dataclass(frozen=True)
class TaskOrderAssignment:
    sequence: int
    group: str
    order: tuple[ExperimentType, ...]

    def position(self, task: ExperimentType | str) -> int:
        return self.order.index(ExperimentType(task)) + 1

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(str(task) for task in self.order)


def assignment_for_sequence(
    sequence: int,
    groups: tuple[str, ...] | None = None,
) -> TaskOrderAssignment:
    """Return the deterministic 1-based participant-sequence assignment."""
    if sequence < 1:
        raise ValidationError("task-order participant sequence must be >= 1")
    ordered_groups = groups or tuple(TASK_ORDER_GROUPS)
    if len(ordered_groups) != 6 or set(ordered_groups) != set(TASK_ORDER_GROUPS):
        raise ValidationError("available task orders must contain FTS, FST, TFS, TSF, SFT and STF")
    group = ordered_groups[(sequence - 1) % len(ordered_groups)]
    return TaskOrderAssignment(sequence, group, TASK_ORDER_GROUPS[group])


def parse_task_order(values: Iterable[ExperimentType | str]) -> tuple[ExperimentType, ...]:
    order = tuple(ExperimentType(value) for value in values)
    if len(order) != 3 or set(order) != set(ExperimentType):
        raise ValidationError("task order must contain Flick, Tracking and Switching exactly once")
    return order


def validate_assignment(group: str, values: Iterable[ExperimentType | str]) -> tuple[ExperimentType, ...]:
    order = parse_task_order(values)
    if group not in TASK_ORDER_GROUPS or TASK_ORDER_GROUPS[group] != order:
        raise ValidationError(f"task-order group {group!r} does not match the stored task order")
    return order


def format_task_order(values: Iterable[ExperimentType | str], short: bool = False) -> str:
    order = parse_task_order(values)
    if short:
        return " → ".join(task.value[0].upper() if task != ExperimentType.SWITCHING else "S" for task in order)
    return " → ".join(TASK_LABELS[task] for task in order)
