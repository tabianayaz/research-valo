"""Persistence data models.

These dataclasses mirror database rows. They intentionally contain only light
validation; domain-level validation (e.g. crosshair parameter ranges) lives in
the corresponding domain modules.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from app.utils.validators import ValidationError, require_positive, validate_player_id


class ExperimentType(StrEnum):
    FLICK = "flick"
    TRACKING = "tracking"
    SWITCHING = "switching"


class Condition(StrEnum):
    """Experimental condition of a session (needed to separate practice effects).

    BASELINE   initial measurement with the standard crosshair (the only profile source)
    STANDARD   repeated control measurement with the same standard crosshair after the
               recommendation; it is NOT a new baseline
    CANDIDATE  measurement with the selected recommended candidate crosshair
    """

    BASELINE = "baseline"
    CANDIDATE = "candidate"
    STANDARD = "standard"


POST_BASELINE_CONDITIONS = (Condition.CANDIDATE, Condition.STANDARD)


class SessionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


class AssessmentStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AssessmentStage(StrEnum):
    PRACTICE = "practice"
    FAMILIARIZATION = "familiarization"  # short non-analysed block after a crosshair change
    EXPERIMENTAL = "experimental"
    COMBINED = "combined"  # legacy/manual single-task window


NON_ANALYSED_STAGES = (AssessmentStage.PRACTICE, AssessmentStage.FAMILIARIZATION)


class EvaluationStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskOrderMode(StrEnum):
    COUNTERBALANCED = "counterbalanced"
    DEBUG_FIXED = "debug_fixed"
    INDIVIDUAL = "individual"


class TrialResult(StrEnum):
    HIT = "hit"
    MISS = "miss"
    TIMEOUT = "timeout"
    TRACKED = "tracked"
    INCOMPLETE = "incomplete"


class TrialStatus(StrEnum):
    """Validity of a trial, separate from its outcome (``TrialResult``).

    VALID                 normal trial
    INVALID_PRE_MOVEMENT  the cursor left the stabilisation region or moved during the
                          foreperiod; no target was shown and the planned trial is repeated
    TIMING_FALLBACK       target onset came from the fallback timer, not from a paint;
                          excluded from reaction/completion time, kept for accuracy
    """

    VALID = "valid"
    INVALID_PRE_MOVEMENT = "invalid_pre_movement"
    TIMING_FALLBACK = "timing_fallback"


class TimingQuality(StrEnum):
    PAINT = "paint"
    FALLBACK = "fallback"
    PREVIOUS_CLICK = "previous_click"
    NOT_APPLICABLE = "not_applicable"


class TrialPhase(StrEnum):
    PRACTICE = "practice"
    EXPERIMENTAL = "experimental"


class CrosshairRole(StrEnum):
    BASELINE = "baseline"
    CANDIDATE = "candidate"
    CUSTOM = "custom"


def _to_json(value: dict[str, Any] | None) -> str | None:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else None


def _from_json(value: str | None) -> dict[str, Any] | None:
    return json.loads(value) if value else None


@dataclass
class Player:
    """Anonymous participant. Must never contain personally identifying data."""

    player_id: str
    fps_experience: str | None = None
    aim_training_frequency: str | None = None
    mouse_dpi: int | None = None
    sensitivity: float | None = None
    edpi: float | None = None
    display_width: int | None = None
    display_height: int | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    task_order_sequence: int | None = None
    task_order_group: str | None = None
    task_order: tuple[str, ...] | None = None
    condition_order_group: str | None = None
    condition_order: tuple[str, ...] | None = None
    condition_assignment_method: str | None = None

    def validate(self) -> None:
        self.player_id = validate_player_id(self.player_id)
        for name in ("mouse_dpi", "sensitivity", "edpi", "display_width", "display_height"):
            value = getattr(self, name)
            if value is not None:
                require_positive(name, value)
        assignment_fields = (self.task_order_sequence, self.task_order_group, self.task_order)
        if any(value is not None for value in assignment_fields):
            if not all(value is not None for value in assignment_fields):
                raise ValidationError("task-order sequence, group and order must be stored together")
            if self.task_order_sequence < 1:
                raise ValidationError("task_order_sequence must be >= 1")
            from app.experiment.task_order import validate_assignment
            validate_assignment(self.task_order_group, self.task_order)
        if self.condition_order_group is not None or self.condition_order is not None:
            from app.experiment.conditions import validate_condition_order
            validate_condition_order(self.condition_order_group, self.condition_order)


@dataclass
class CrosshairRecord:
    """Database representation of a crosshair configuration.

    The domain model ``CrosshairConfig`` (Milestone 2) converts to/from this.
    """

    name: str
    role: CrosshairRole
    color: str
    size: float
    thickness: float
    gap: float
    outline_enabled: bool
    outline_thickness: float
    opacity: float
    source_id: int | None = None
    fidelity: str | None = None
    crosshair_id: int | None = None
    created_at: str | None = None

    def parameter_dict(self) -> dict[str, Any]:
        """Only the visual parameters (used for hashing / de-duplication)."""
        return {
            "color": self.color.lower(),
            "size": float(self.size),
            "thickness": float(self.thickness),
            "gap": float(self.gap),
            "outline_enabled": bool(self.outline_enabled),
            "outline_thickness": float(self.outline_thickness),
            "opacity": float(self.opacity),
        }


class ImportMethod(StrEnum):
    SCRAPER = "scraper"
    CSV = "csv"
    JSON = "json"
    MANUAL = "manual"
    BUILTIN = "builtin"


@dataclass
class CrosshairSource:
    """Provenance of one externally obtained crosshair (kept separate from measurements)."""

    source_name: str
    import_method: ImportMethod
    source_url: str | None = None
    source_player: str | None = None
    source_format: str | None = None
    source_code: str | None = None
    raw_payload: dict[str, Any] | None = None
    notes: str | None = None
    source_id: int | None = None
    retrieved_at: str | None = None


@dataclass
class SourceListing:
    """A source row joined with the crosshair derived from it (if any)."""

    source: CrosshairSource
    crosshair: CrosshairRecord | None


@dataclass
class Environment:
    """Snapshot of measurement conditions for one session."""

    display_width: int | None = None
    display_height: int | None = None
    app_width: int | None = None
    app_height: int | None = None
    device_pixel_ratio: float | None = None
    refresh_rate_hz: float | None = None
    measured_fps: float | None = None
    fov: float | None = None
    background_color: str | None = None
    background_condition: str | None = None
    target_color: str | None = None
    target_size: float | None = None
    target_speed: float | None = None
    mouse_dpi: int | None = None
    sensitivity: float | None = None
    extra: dict[str, Any] | None = None
    environment_id: int | None = None
    created_at: str | None = None

    def extra_json(self) -> str | None:
        return _to_json(self.extra)


@dataclass
class Session:
    player_id: str
    experiment_type: ExperimentType
    condition: Condition
    session_number: int
    crosshair_id: int
    environment_id: int | None = None
    random_seed: int | None = None
    task_config: dict[str, Any] | None = None
    parent_session_id: int | None = None
    recommendation_id: int | None = None
    app_version: str | None = None
    notes: str | None = None
    status: SessionStatus = SessionStatus.IN_PROGRESS
    session_id: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    protocol_version: str | None = None
    protocol_snapshot: dict[str, Any] | None = None
    crosshair_snapshot: dict[str, Any] | None = None
    assessment_id: int | None = None
    assessment_stage: AssessmentStage | None = None
    task_order_mode: TaskOrderMode | None = None
    task_order_group: str | None = None
    task_order: tuple[str, ...] | None = None
    task_position: int | None = None
    evaluation_id: int | None = None
    condition_order_group: str | None = None
    condition_order: tuple[str, ...] | None = None
    condition_position: int | None = None
    initial_baseline_session_id: int | None = None
    selected_candidate_id: int | None = None
    seed_group: str | None = None

    def validate(self) -> None:
        if self.session_number < 1:
            raise ValidationError("session_number must be >= 1")
        ExperimentType(self.experiment_type)
        condition = Condition(self.condition)
        if self.assessment_stage is not None:
            AssessmentStage(self.assessment_stage)
        if self.task_order_mode is not None:
            TaskOrderMode(self.task_order_mode)
        if self.task_position is not None and not 1 <= self.task_position <= 3:
            raise ValidationError("task_position must be between 1 and 3")
        if self.condition_position is not None:
            if not 1 <= self.condition_position <= 2:
                raise ValidationError("condition_position must be 1 or 2")
            if condition == Condition.BASELINE:
                raise ValidationError("a baseline session has no post-baseline condition position")
        if self.condition_order_group is not None or self.condition_order is not None:
            from app.experiment.conditions import validate_condition_order
            order = validate_condition_order(self.condition_order_group, self.condition_order)
            if self.condition_position is not None and order[self.condition_position - 1] != condition:
                raise ValidationError("condition_position does not match condition in condition_order")
        if self.evaluation_id is not None and condition == Condition.BASELINE:
            raise ValidationError("an evaluation session must be a standard or candidate condition")
        if self.seed_group is not None:
            from app.experiment.conditions import SEED_GROUPS
            if self.seed_group not in SEED_GROUPS:
                raise ValidationError(f"unknown seed_group {self.seed_group!r}")
        if self.task_order is not None:
            from app.experiment.task_order import parse_task_order
            order = parse_task_order(self.task_order)
            if self.task_position is not None \
                    and order[self.task_position - 1] != ExperimentType(self.experiment_type):
                raise ValidationError("task_position does not match experiment_type in task_order")


@dataclass
class TaskAssessment:
    """Persisted progress through practice and experimental task sequences."""

    player_id: str
    condition: Condition
    crosshair_id: int
    task_order_group: str
    task_order: tuple[str, ...]
    practice_task_order: tuple[str, ...]
    stage: AssessmentStage
    current_position: int
    current_task: ExperimentType | None
    completed_tasks: dict[str, list[str]] = field(
        default_factory=lambda: {"practice": [], "experimental": []}
    )
    protocol_version: str | None = None
    protocol_snapshot: dict[str, Any] | None = None
    recommendation_id: int | None = None
    status: AssessmentStatus = AssessmentStatus.IN_PROGRESS
    assessment_id: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    evaluation_id: int | None = None
    condition_position: int | None = None

    def order_for_stage(self, stage: AssessmentStage | None = None) -> tuple[str, ...]:
        """Pre-experimental blocks (practice / familiarization) use the stored practice order."""
        selected = AssessmentStage(stage or self.stage)
        return self.practice_task_order if selected in NON_ANALYSED_STAGES else self.task_order

    def validate(self) -> None:
        validate_player_id(self.player_id)
        Condition(self.condition)
        AssessmentStatus(self.status)
        stage = AssessmentStage(self.stage)
        if stage == AssessmentStage.COMBINED:
            raise ValidationError("controlled assessment stage cannot be combined")
        if not 1 <= self.current_position <= 3:
            raise ValidationError("current_position must be between 1 and 3")
        from app.experiment.task_order import parse_task_order, validate_assignment
        validate_assignment(self.task_order_group, self.task_order)
        parse_task_order(self.practice_task_order)
        if self.current_task is not None:
            expected = ExperimentType(self.order_for_stage()[self.current_position - 1])
            if ExperimentType(self.current_task) != expected:
                raise ValidationError("current_task does not match stage and current_position")
        if (self.evaluation_id is None) != (self.condition_position is None):
            raise ValidationError("evaluation_id and condition_position must be stored together")
        if self.evaluation_id is not None and Condition(self.condition) == Condition.BASELINE:
            raise ValidationError("an evaluation assessment must be a standard or candidate condition")
        if stage == AssessmentStage.FAMILIARIZATION and self.evaluation_id is None:
            raise ValidationError("familiarization is only used in post-baseline condition assessments")


@dataclass
class ConditionEvaluation:
    """One post-baseline evaluation cycle: Candidate and Standard in a fixed, counterbalanced order.

    Everything that defines the cycle (recommendation run, selected candidate,
    initial baseline sessions, standard crosshair snapshot and condition order)
    is fixed when the cycle starts and is immutable in the database.
    """

    player_id: str
    recommendation_id: int
    selected_candidate_id: int
    standard_crosshair_id: int
    standard_crosshair_snapshot: dict[str, Any]
    initial_baseline_sessions: dict[str, int]
    condition_order_group: str
    condition_order: tuple[str, ...]
    condition_assignment_method: str
    current_position: int = 1
    status: EvaluationStatus = EvaluationStatus.IN_PROGRESS
    protocol_version: str | None = None
    protocol_snapshot: dict[str, Any] | None = None
    evaluation_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def current_condition(self) -> Condition:
        return Condition(self.condition_order[self.current_position - 1])

    def position_of(self, condition: Condition | str) -> int:
        return self.condition_order.index(str(Condition(condition))) + 1

    def validate(self) -> None:
        validate_player_id(self.player_id)
        EvaluationStatus(self.status)
        if not 1 <= self.current_position <= 2:
            raise ValidationError("current_position must be 1 or 2")
        from app.experiment.conditions import validate_condition_order
        validate_condition_order(self.condition_order_group, self.condition_order)
        if set(self.initial_baseline_sessions) != {str(t) for t in ExperimentType}:
            raise ValidationError("an evaluation needs one initial baseline session per task")


@dataclass
class Trial:
    """One raw trial. Once stored it is immutable."""

    session_id: int
    trial_number: int
    task_type: ExperimentType
    result: TrialResult
    target_id: str | None = None
    previous_target_id: str | None = None
    target_x: float | None = None
    target_y: float | None = None
    target_size: float | None = None
    target_distance: float | None = None
    target_speed: float | None = None
    initial_crosshair_x: float | None = None
    initial_crosshair_y: float | None = None
    reaction_time_ms: float | None = None
    movement_time_ms: float | None = None
    completion_time_ms: float | None = None
    error_distance: float | None = None
    movement_distance: float | None = None
    extra: dict[str, Any] | None = None
    trial_status: TrialStatus | None = None
    timing_quality: TimingQuality | None = None
    trial_phase: TrialPhase | None = None
    trial_id: int | None = None
    recorded_at: str | None = None

    def validate(self) -> None:
        if self.trial_number < 1:
            raise ValidationError("trial_number must be >= 1")
        ExperimentType(self.task_type)
        TrialResult(self.result)
        for enum, value in ((TrialStatus, self.trial_status), (TimingQuality, self.timing_quality),
                            (TrialPhase, self.trial_phase)):
            if value is not None:
                enum(value)

    def extra_json(self) -> str | None:
        return _to_json(self.extra)


@dataclass
class TrialSample:
    """A single cursor/target sample within a trial (trajectory point)."""

    t_ms: float
    cursor_x: float
    cursor_y: float
    target_x: float | None = None
    target_y: float | None = None
    on_target: bool | None = None


@dataclass
class TrialEvent:
    """A discrete input event within a trial (e.g. a click)."""

    t_ms: float
    event_type: str
    x: float | None = None
    y: float | None = None
    is_hit: bool | None = None


@dataclass
class SessionSummary:
    """Lightweight row used by history/list views."""

    session_id: int
    player_id: str
    started_at: str
    experiment_type: str
    condition: str
    session_number: int
    status: str
    crosshair_name: str
    trial_count: int = 0
    task_order_group: str | None = None
    task_order: tuple[str, ...] | None = None
    task_position: int | None = None
    assessment_stage: str | None = None
    condition_order_group: str | None = None
    condition_position: int | None = None
    evaluation_id: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)


__all__ = [
    "Condition",
    "ConditionEvaluation",
    "EvaluationStatus",
    "NON_ANALYSED_STAGES",
    "POST_BASELINE_CONDITIONS",
    "AssessmentStage",
    "AssessmentStatus",
    "CrosshairRecord",
    "CrosshairRole",
    "CrosshairSource",
    "ImportMethod",
    "SourceListing",
    "Environment",
    "ExperimentType",
    "Player",
    "Session",
    "SessionStatus",
    "SessionSummary",
    "TaskAssessment",
    "TaskOrderMode",
    "Trial",
    "TrialEvent",
    "TrialResult",
    "TrialSample",
    "dataclass_to_dict",
]
