"""Post-baseline condition order (Candidate / Standard) and its deterministic assignment.

Design
    Initial BASELINE (standard crosshair) -> recommendation from that baseline only
    -> two post-baseline conditions tested by the same participant:
       group CS: Candidate -> Standard
       group SC: Standard  -> Candidate

Assignment (``participant_sequence_alternating_crossed_6x2``)
    Uses the participant's immutable creation sequence, which already drives
    the task-order rotation (``app.experiment.task_order``)::

        index = ((sequence - 1) + (sequence - 1) // 6) % 2   -> CS if 0 else SC

    Consecutive participants alternate CS / SC, and the alternation flips after
    every six participants, so each block of 12 participants contains every
    task order (FTS ... STF) exactly once with CS and once with SC. Task order
    and condition order therefore stay separate and are not confounded.

    The group is stored on the participant and never recomputed. This is an
    implementation/allocation method (PLACEHOLDER), not a claim that the
    method is scientifically superior; the final allocation is a research decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.data.models import Condition, ExperimentType
from app.utils.validators import ValidationError

CONDITION_ORDER_METHOD = "counterbalanced"
CONDITION_ASSIGNMENT_METHOD = "participant_sequence_alternating_crossed_6x2"

CONDITION_ORDER_GROUPS: dict[str, tuple[Condition, Condition]] = {
    "CS": (Condition.CANDIDATE, Condition.STANDARD),
    "SC": (Condition.STANDARD, Condition.CANDIDATE),
}

# seed_group stored with every session: which seed family produced its target plan.
SEED_GROUPS = ("baseline", "standard", "candidate", "practice", "familiarization")


@dataclass(frozen=True)
class ConditionOrderAssignment:
    group: str
    order: tuple[Condition, Condition]
    method: str = CONDITION_ASSIGNMENT_METHOD

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(str(condition) for condition in self.order)

    def position(self, condition: Condition | str) -> int:
        return self.order.index(Condition(condition)) + 1


def condition_order_for_sequence(sequence: int) -> ConditionOrderAssignment:
    """Deterministic CS/SC group for a 1-based participant sequence."""
    if sequence < 1:
        raise ValidationError("condition-order participant sequence must be >= 1")
    index = ((sequence - 1) + (sequence - 1) // 6) % 2
    group = ("CS", "SC")[index]
    return ConditionOrderAssignment(group, CONDITION_ORDER_GROUPS[group])


def parse_condition_order(values: Iterable[Condition | str]) -> tuple[Condition, ...]:
    order = tuple(Condition(value) for value in values)
    if len(order) != 2 or set(order) != {Condition.CANDIDATE, Condition.STANDARD}:
        raise ValidationError("condition order must contain Candidate and Standard exactly once")
    return order


def validate_condition_order(group: str | None, values: Iterable[Condition | str] | None) -> tuple[Condition, ...]:
    if group is None or values is None:
        raise ValidationError("condition-order group and order must be stored together")
    order = parse_condition_order(values)
    if group not in CONDITION_ORDER_GROUPS or CONDITION_ORDER_GROUPS[group] != order:
        raise ValidationError(f"condition-order group {group!r} does not match the stored condition order")
    return order


def seed_group_for(condition: Condition | str, stage: str | None) -> str:
    """Seed family of a session: practice / familiarization blocks have their own seeds."""
    if stage in ("practice", "familiarization"):
        return str(stage)
    return str(Condition(condition))


def task_values() -> tuple[str, ...]:
    return tuple(str(task) for task in ExperimentType)
