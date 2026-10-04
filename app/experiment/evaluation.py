"""Post-baseline crosshair evaluation cycle (Phase 5).

Flow::

    initial BASELINE (three tasks, standard crosshair)
    -> profile + recommendation from those initial baseline sessions only
    -> the participant selects one candidate (fixed afterwards)
    -> stored condition order CS or SC (``app.experiment.conditions``)
    -> condition 1 -> condition 2 (each a controlled three-task assessment
       with a familiarization block) -> descriptive three-condition comparison

STANDARD repeats the exact crosshair of the initial baseline sessions (taken
from their stored crosshair snapshot, never from the current configuration
file). Nothing here infers metadata for historical sessions.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.crosshair.config import FIELDS
from app.data.models import (
    NON_ANALYSED_STAGES,
    AssessmentStatus,
    Condition,
    ConditionEvaluation,
    CrosshairRecord,
    EvaluationStatus,
    ExperimentType,
    Session,
    SessionStatus,
    TaskAssessment,
)
from app.data.repository import Repository
from app.analysis.profile import initial_baseline_sessions

SNAPSHOT_KEYS = (*FIELDS, "px_per_unit")


class EvaluationError(Exception):
    """The evaluation cannot start or continue; the message is shown to the researcher."""


def crosshair_snapshot(record: CrosshairRecord, px_per_unit: float) -> dict[str, Any]:
    """Same shape as the ``crosshair_snapshot`` stored with every session."""
    return {**asdict(record), "px_per_unit": px_per_unit}


def _normalized(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key == "color":
        return str(value).upper()
    if key == "outline_enabled":
        return bool(value)
    return round(float(value), 9)


def snapshot_differences(reference: dict[str, Any] | None, other: dict[str, Any] | None) -> list[str]:
    """Rendering-relevant keys whose values differ (missing snapshots differ in every key)."""
    if not reference or not other:
        return list(SNAPSHOT_KEYS)
    return [key for key in SNAPSHOT_KEYS
            if _normalized(key, reference.get(key)) != _normalized(key, other.get(key))]


# ----------------------------------------------------------------- baseline
def baseline_problems(repo: Repository, player_id: str) -> tuple[dict[str, Session], list[str]]:
    """Initial completed baseline session per task and the reasons they cannot define a cycle."""
    found = {str(task): session for task, session in initial_baseline_sessions(repo, player_id).items()}
    problems: list[str] = []
    missing = [str(task) for task in ExperimentType if str(task) not in found]
    if missing:
        problems.append(f"Missing initial completed baseline session for: {', '.join(missing)}")
        return found, problems
    sessions = list(found.values())
    if len({s.crosshair_id for s in sessions}) != 1:
        problems.append("The initial baseline sessions did not use the same standard crosshair.")
    if any(s.crosshair_snapshot is None for s in sessions):
        problems.append("An initial baseline session has no stored crosshair snapshot.")
    else:
        reference = sessions[0].crosshair_snapshot
        if any(snapshot_differences(reference, s.crosshair_snapshot) for s in sessions[1:]):
            problems.append("The crosshair snapshots of the initial baseline sessions differ.")
    return found, problems


def recommendation_source_problems(repo: Repository, recommendation: dict[str, Any],
                                   initial: dict[str, Session]) -> list[str]:
    """``recommendation_source_session_id`` check: the run must come from the initial baselines only."""
    problems: list[str] = []
    sources = [int(s) for s in recommendation.get("source_session_ids") or []]
    expected = sorted(session.session_id for session in initial.values())
    if sorted(sources) != expected:
        problems.append(
            f"Recommendation #{recommendation['recommendation_id']} was not generated from the initial "
            f"baseline sessions (sources {sorted(sources)}, initial baselines {expected})."
        )
    for session_id in sources:
        session = repo.get_session(session_id)
        if session is None or session.player_id != recommendation["player_id"] \
                or Condition(session.condition) != Condition.BASELINE \
                or session.status != SessionStatus.COMPLETED \
                or session.assessment_stage in NON_ANALYSED_STAGES:
            problems.append(f"Source session #{session_id} is not a completed baseline session of this participant.")
    return problems


def current_standard_differences(configured: CrosshairRecord, px_per_unit: float,
                                 baseline_snapshot: dict[str, Any] | None) -> list[str]:
    """Differences between the currently configured standard crosshair and the baseline snapshot."""
    return snapshot_differences(baseline_snapshot, crosshair_snapshot(configured, px_per_unit))


# ---------------------------------------------------------------- the cycle
def start_evaluation(repo: Repository, protocol, player_id: str, recommendation_id: int,
                     candidate_id: int) -> ConditionEvaluation:
    """Fix the selected candidate, standard snapshot and condition order for one cycle."""
    player = repo.get_player(player_id)
    if player is None:
        raise EvaluationError(f"Unknown participant {player_id!r}.")
    if player.condition_order_group is None:
        player = repo.save_player(player)
    recommendation = repo.get_recommendation(recommendation_id)
    if recommendation is None or recommendation["player_id"] != player_id:
        raise EvaluationError(f"Recommendation #{recommendation_id} does not belong to this participant.")
    if candidate_id not in {c["crosshair_id"] for c in recommendation["candidates"]}:
        raise EvaluationError(f"Crosshair #{candidate_id} is not a candidate of recommendation #{recommendation_id}.")
    initial, problems = baseline_problems(repo, player_id)
    problems += [] if problems else recommendation_source_problems(repo, recommendation, initial)
    if problems:
        raise EvaluationError(" ".join(problems))
    reference = initial[str(ExperimentType.FLICK)]
    standard = repo.get_crosshair(reference.crosshair_id)
    if standard is None or snapshot_differences(
            reference.crosshair_snapshot,
            crosshair_snapshot(standard, reference.crosshair_snapshot.get("px_per_unit"))):
        raise EvaluationError("The stored standard crosshair no longer matches the baseline crosshair snapshot.")
    return repo.create_condition_evaluation(ConditionEvaluation(
        player_id=player_id,
        recommendation_id=recommendation_id,
        selected_candidate_id=candidate_id,
        standard_crosshair_id=standard.crosshair_id,
        standard_crosshair_snapshot=dict(reference.crosshair_snapshot),
        initial_baseline_sessions={task: s.session_id for task, s in initial.items()},
        condition_order_group=player.condition_order_group,
        condition_order=tuple(player.condition_order),
        condition_assignment_method=player.condition_assignment_method,
        protocol_version=protocol.version,
        protocol_snapshot=protocol.stored_snapshot(),
    ))


def condition_crosshair(repo: Repository, evaluation: ConditionEvaluation,
                        condition: Condition | str) -> CrosshairRecord:
    if Condition(condition) == Condition.CANDIDATE:
        record = repo.get_crosshair(evaluation.selected_candidate_id)
    else:
        record = repo.get_crosshair(evaluation.standard_crosshair_id)
        if record is not None and snapshot_differences(
                evaluation.standard_crosshair_snapshot,
                crosshair_snapshot(record, evaluation.standard_crosshair_snapshot.get("px_per_unit"))):
            raise EvaluationError("The stored standard crosshair no longer matches the baseline crosshair snapshot.")
    if record is None:
        raise EvaluationError("The crosshair of this condition no longer exists.")
    return record


def start_or_resume_condition_assessment(repo: Repository, protocol,
                                         evaluation: ConditionEvaluation) -> TaskAssessment:
    """Controlled three-task assessment of the evaluation's current condition (resumed if unfinished)."""
    evaluation = repo.advance_condition_evaluation(evaluation.evaluation_id)
    if evaluation.status == EvaluationStatus.COMPLETED:
        raise EvaluationError("This crosshair evaluation is already complete.")
    existing = repo.get_evaluation_task_assessment(evaluation.evaluation_id, evaluation.current_position)
    condition = evaluation.current_condition
    crosshair = condition_crosshair(repo, evaluation, condition)
    if existing is not None and existing.status == AssessmentStatus.IN_PROGRESS:
        return repo.recover_task_assessment(existing.assessment_id)
    return repo.start_or_resume_task_assessment(
        evaluation.player_id, condition, crosshair.crosshair_id, evaluation.recommendation_id, protocol,
        evaluation_id=evaluation.evaluation_id, condition_position=evaluation.current_position,
    )


def session_link(evaluation: ConditionEvaluation, assessment: TaskAssessment,
                 task: ExperimentType | str) -> dict[str, Any]:
    """Session-linking fields of one post-baseline condition session."""
    initial = evaluation.initial_baseline_sessions[str(task)]
    return {
        "parent_session_id": initial,
        "initial_baseline_session_id": initial,
        "evaluation_id": evaluation.evaluation_id,
        "condition_order_group": evaluation.condition_order_group,
        "condition_order": tuple(evaluation.condition_order),
        "condition_position": assessment.condition_position,
        "selected_candidate_id": evaluation.selected_candidate_id,
        "recommendation_id": evaluation.recommendation_id,
    }


def evaluation_sessions(repo: Repository, evaluation: ConditionEvaluation) -> dict[str, dict[str, Session]]:
    """Completed analysed sessions of the cycle: ``{condition: {task: session}}`` (baseline = initial)."""
    result: dict[str, dict[str, Session]] = {str(Condition.BASELINE): {}}
    for task, session_id in evaluation.initial_baseline_sessions.items():
        session = repo.get_session(int(session_id))
        if session is not None:
            result[str(Condition.BASELINE)][task] = session
    for condition in (Condition.STANDARD, Condition.CANDIDATE):
        result[str(condition)] = {}
        for session in repo.list_sessions(evaluation.player_id, condition=condition,
                                          status=SessionStatus.COMPLETED,
                                          evaluation_id=evaluation.evaluation_id):
            if session.assessment_stage in NON_ANALYSED_STAGES:
                continue
            result[str(condition)].setdefault(str(session.experiment_type), session)
    return result
