"""Central experiment protocol and its per-session snapshot.

The protocol gathers every value that defines how a session is run: practice
settings, task order, the per-task parameters (trial count, target size and
distances, tracking duration and path/speed, timeout, foreperiod range,
stabilisation radius / movement threshold / hold duration, random seed),
the arena background, the crosshair unit scale, the standard (baseline)
crosshair, the post-baseline condition design (Candidate / Standard order,
condition seeds, familiarization, rest) and the timing-procedure version.

``protocol_version`` is ``<label>+<hash>`` where the hash covers the whole
snapshot. Changing any value therefore produces a new version automatically,
and each session stores the exact snapshot it was run with
(``sessions.protocol_snapshot_json``), so historical sessions stay
interpretable without the current configuration file.

All current values are placeholders (``protocol.confirmed = false``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.config.research import ResearchParameters
from app.experiment.conditions import (
    CONDITION_ASSIGNMENT_METHOD,
    CONDITION_ORDER_GROUPS,
    CONDITION_ORDER_METHOD,
)
from app.experiment.task_order import (
    ASSIGNMENT_METHOD,
    TASK_ORDER_GROUPS,
    TASK_ORDER_METHOD,
    assignment_for_sequence,
    parse_task_order,
)
from app.experiment.timing import TIMING_VERSION
from app.utils.validators import ValidationError

PROTOCOL_SCHEMA = "protocol-3"
TASKS = ("flick", "tracking", "switching")


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ExperimentProtocol:
    label: str
    confirmed: bool
    practice_enabled: bool
    practice_trial_count: dict[str, int]
    practice_random_seed: dict[str, int]
    task_order_method: str
    assignment_method: str
    available_task_orders: tuple[str, ...]
    practice_task_order_method: str
    practice_fixed_task_order: tuple[str, ...]
    debug_task_selection_enabled: bool
    debug_fixed_task_order: tuple[str, ...]
    condition_order_method: str
    condition_assignment_method: str
    available_condition_orders: tuple[str, ...]
    condition_random_seed: dict[str, dict[str, int]]
    condition_familiarization_enabled: bool
    condition_familiarization_trial_count: dict[str, int]
    condition_familiarization_random_seed: dict[str, int]
    condition_rest_seconds: float
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    baseline_crosshair: dict[str, Any] = field(default_factory=dict)

    def practice_count(self, task: str) -> int:
        return self.practice_trial_count.get(str(task), 0) if self.practice_enabled else 0

    def familiarization_count(self, task: str) -> int:
        if not self.condition_familiarization_enabled:
            return 0
        return self.condition_familiarization_trial_count.get(str(task), 0)

    def pre_block_count(self, stage: str, task: str) -> int:
        """Trials of the non-analysed block before the experimental trials of ``stage``."""
        return self.familiarization_count(task) if str(stage) == "familiarization" else self.practice_count(task)

    def pre_block_seed(self, stage: str, task: str) -> int:
        if str(stage) == "familiarization":
            return self.condition_familiarization_random_seed[str(task)]
        return self.practice_random_seed[str(task)]

    def experimental_seed(self, condition: str, task: str, baseline_seed: int) -> int:
        """Different seed per condition (same parameter distributions, different target sequence).

        BASELINE keeps the task's own ``random_seed`` so earlier baseline sessions stay reproducible.
        """
        if str(condition) == "baseline":
            return baseline_seed
        return self.condition_random_seed[str(condition)][str(task)]

    def practice_order(self, assigned_order: tuple[str, ...]) -> tuple[str, ...]:
        if self.practice_task_order_method == "match_assigned":
            return tuple(str(task) for task in parse_task_order(assigned_order))
        return self.practice_fixed_task_order

    def snapshot(self) -> dict[str, Any]:
        """Everything that defines the protocol (without the derived version)."""
        return {
            "schema": PROTOCOL_SCHEMA,
            "label": self.label,
            "confirmed": self.confirmed,
            "practice": {
                "enabled": self.practice_enabled,
                "trial_count": dict(self.practice_trial_count),
                "random_seed": dict(self.practice_random_seed),
                "task_order_method": self.practice_task_order_method,
                "fixed_task_order": list(self.practice_fixed_task_order),
            },
            "task_order_method": self.task_order_method,
            "available_task_orders": list(self.available_task_orders),
            "assignment_method": self.assignment_method,
            "debug": {
                "task_selection_enabled": self.debug_task_selection_enabled,
                "fixed_task_order": list(self.debug_fixed_task_order),
                "experimental": False,
            },
            "condition_design": {
                "conditions": ["baseline", "standard", "candidate"],
                "condition_order_method": self.condition_order_method,
                "condition_assignment_method": self.condition_assignment_method,
                "available_condition_orders": list(self.available_condition_orders),
                "random_seed": {k: dict(v) for k, v in self.condition_random_seed.items()},
                "familiarization": {
                    "enabled": self.condition_familiarization_enabled,
                    "trial_count": dict(self.condition_familiarization_trial_count),
                    "random_seed": dict(self.condition_familiarization_random_seed),
                },
                "rest_seconds": self.condition_rest_seconds,
            },
            "tasks": {name: dict(values) for name, values in self.tasks.items()},
            "environment": dict(self.environment),
            "baseline_crosshair": dict(self.baseline_crosshair),
            "timing_version": TIMING_VERSION,
        }

    @property
    def version(self) -> str:
        digest = hashlib.sha256(_canonical(self.snapshot()).encode("utf-8")).hexdigest()[:12]
        return f"{self.label}+{digest}"

    def stored_snapshot(self) -> dict[str, Any]:
        return {**self.snapshot(), "protocol_version": self.version}


def build_protocol(research: ResearchParameters) -> ExperimentProtocol:
    """Protocol from the current research parameters (read at session start)."""
    data = research.protocol
    try:
        protocol = ExperimentProtocol(
            label=str(data["label"]),
            confirmed=bool(data["confirmed"]),
            practice_enabled=bool(data["practice_enabled"]),
            practice_trial_count={t: int(data["practice_trial_count"][t]) for t in TASKS},
            practice_random_seed={t: int(data["practice_random_seed"][t]) for t in TASKS},
            task_order_method=str(data["task_order_method"]),
            assignment_method=str(data["assignment_method"]),
            available_task_orders=tuple(str(group) for group in data["available_task_orders"]),
            practice_task_order_method=str(data["practice_task_order_method"]),
            practice_fixed_task_order=tuple(str(t) for t in data["practice_fixed_task_order"]),
            debug_task_selection_enabled=bool(data["debug_task_selection_enabled"]),
            debug_fixed_task_order=tuple(str(t) for t in data["debug_fixed_task_order"]),
            condition_order_method=str(data["condition_order_method"]),
            condition_assignment_method=str(data["condition_assignment_method"]),
            available_condition_orders=tuple(str(g) for g in data["available_condition_orders"]),
            condition_random_seed={
                c: {t: int(data["condition_random_seed"][c][t]) for t in TASKS} for c in ("standard", "candidate")
            },
            condition_familiarization_enabled=bool(data["condition_familiarization_enabled"]),
            condition_familiarization_trial_count={
                t: int(data["condition_familiarization_trial_count"][t]) for t in TASKS
            },
            condition_familiarization_random_seed={
                t: int(data["condition_familiarization_random_seed"][t]) for t in TASKS
            },
            condition_rest_seconds=float(data["condition_rest_seconds"]),
            tasks={t: dict(research.task_parameters(t)) for t in TASKS},
            environment={
                "experiment_background_color": research.experiment_background_color,
                "px_per_unit": research.px_per_unit,
            },
            baseline_crosshair={**research.baseline_crosshair, "confirmed": research.baseline_confirmed},
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid protocol parameters: {exc}") from exc
    problems = []
    if not protocol.label or "+" in protocol.label:
        problems.append("label must be non-empty and must not contain '+'")
    if any(n < 0 for n in protocol.practice_trial_count.values()):
        problems.append("practice_trial_count must be >= 0")
    if protocol.task_order_method != TASK_ORDER_METHOD:
        problems.append(f"task_order_method must be {TASK_ORDER_METHOD!r}")
    if protocol.assignment_method != ASSIGNMENT_METHOD:
        problems.append(f"assignment_method must be {ASSIGNMENT_METHOD!r}")
    try:
        assignment_for_sequence(1, protocol.available_task_orders)
    except ValidationError as exc:
        problems.append(str(exc))
    if protocol.practice_task_order_method not in ("match_assigned", "fixed"):
        problems.append("practice_task_order_method must be 'match_assigned' or 'fixed'")
    for name, order in (("practice_fixed_task_order", protocol.practice_fixed_task_order),
                        ("debug_fixed_task_order", protocol.debug_fixed_task_order)):
        try:
            parse_task_order(order)
        except ValidationError as exc:
            problems.append(f"{name}: {exc}")
    if tuple(TASK_ORDER_GROUPS) != protocol.available_task_orders:
        problems.append("available_task_orders must use the configured six-group rotation order")
    if protocol.condition_order_method != CONDITION_ORDER_METHOD:
        problems.append(f"condition_order_method must be {CONDITION_ORDER_METHOD!r}")
    if protocol.condition_assignment_method != CONDITION_ASSIGNMENT_METHOD:
        problems.append(f"condition_assignment_method must be {CONDITION_ASSIGNMENT_METHOD!r}")
    if set(protocol.available_condition_orders) != set(CONDITION_ORDER_GROUPS) \
            or len(protocol.available_condition_orders) != len(CONDITION_ORDER_GROUPS):
        problems.append("available_condition_orders must be CS and SC")
    if any(n < 0 for n in protocol.condition_familiarization_trial_count.values()):
        problems.append("condition_familiarization_trial_count must be >= 0")
    if protocol.condition_rest_seconds < 0:
        problems.append("condition_rest_seconds must be >= 0")
    experimental_seeds = {
        "baseline": {t: int(protocol.tasks[t]["random_seed"]) for t in TASKS},
        **protocol.condition_random_seed,
    }
    for task in TASKS:
        if len({seeds[task] for seeds in experimental_seeds.values()}) != len(experimental_seeds):
            problems.append(f"baseline, standard and candidate seeds must differ for {task}")
    if problems:
        raise ValidationError("Invalid protocol parameters: " + "; ".join(problems))
    return protocol
