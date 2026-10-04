"""Phase 5: Baseline / Standard / Candidate conditions and their counterbalanced order."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter

import pytest
from PySide6.QtCore import QPointF, Qt

from app.analysis.comparison import (
    CONDITION_CSV_HEADER,
    MetricComparison,
    compare_conditions,
    compare_evaluation,
)
from app.analysis.export import CONDITION_COLUMNS, SESSION_ORDER_COLUMNS, export_session
from app.analysis.metrics import analyze_session
from app.analysis.profile import PROFILE_RULE, build_profile
from app.config.research import load_research_parameters
from app.data import database as database_module
from app.data.database import Database, DatabaseError
from app.data.models import (
    NON_ANALYSED_STAGES,
    AssessmentStage,
    AssessmentStatus,
    Condition,
    CrosshairRecord,
    CrosshairRole,
    EvaluationStatus,
    ExperimentType,
    Player,
    Session,
    SessionStatus,
    TaskOrderMode,
    TrialPhase,
)
from app.data.repository import Repository, RepositoryError
from app.experiment.conditions import (
    CONDITION_ASSIGNMENT_METHOD,
    CONDITION_ORDER_GROUPS,
    condition_order_for_sequence,
    seed_group_for,
)
from app.experiment.evaluation import (
    EvaluationError,
    condition_crosshair,
    crosshair_snapshot,
    current_standard_differences,
    evaluation_sessions,
    recommendation_source_problems,
    session_link,
    start_evaluation,
    start_or_resume_condition_assessment,
)
from app.experiment.flick import FlickConfig, generate_plan
from app.experiment.protocol import PROTOCOL_SCHEMA, build_protocol
from app.experiment.task_order import assignment_for_sequence
from app.recommendation.engine import score_candidates, store_recommendation
from app.ui.experiment_window import RunSetup
from app.utils.validators import ValidationError
from experiment_helpers import click, move, press_key, start_trial

FORBIDDEN_WORDS = re.compile(r"\b(better|worse|improved|optimal|best)\b", re.IGNORECASE)


# ------------------------------------------------------------------ helpers
def _candidate(name: str, **changes) -> CrosshairRecord:
    values = dict(color="#00FFFF", size=4, thickness=2, gap=2, outline_enabled=False,
                  outline_thickness=1, opacity=1.0, fidelity="exact")
    values.update(changes)
    return CrosshairRecord(name=name, role=CrosshairRole.CANDIDATE, **values)


def _complete(repo: Repository, protocol, assessment, evaluation=None, snapshot=None):
    """Store and complete the current task of an assessment without trial data."""
    task = str(assessment.current_task)
    stage = AssessmentStage(assessment.stage)
    pre = stage in NON_ANALYSED_STAGES
    link = session_link(evaluation, assessment, task) if evaluation is not None else {}
    session = repo.create_session(Session(
        player_id=assessment.player_id,
        experiment_type=assessment.current_task,
        condition=assessment.condition,
        session_number=repo.next_session_number(assessment.player_id),
        crosshair_id=assessment.crosshair_id,
        random_seed=(protocol.pre_block_seed(str(stage), task) if pre
                     else protocol.experimental_seed(str(assessment.condition), task, 1)),
        assessment_id=assessment.assessment_id,
        assessment_stage=stage,
        task_order_mode=TaskOrderMode.COUNTERBALANCED,
        task_order_group=assessment.task_order_group,
        task_order=assessment.order_for_stage(),
        task_position=assessment.current_position,
        protocol_version=assessment.protocol_version,
        protocol_snapshot=assessment.protocol_snapshot,
        crosshair_snapshot=snapshot,
        seed_group=seed_group_for(assessment.condition, str(stage) if pre else None),
        **link,
    ))
    repo.finish_session(session.session_id, SessionStatus.COMPLETED)
    return repo.complete_task_assessment_session(assessment.assessment_id, session.session_id), session


def _baseline(context):
    """Complete the initial three-task baseline and generate one recommendation run."""
    repo = context.repository
    protocol = build_protocol(context.research)
    player = context.current_player
    base = context.baseline_crosshair
    snapshot = crosshair_snapshot(base, context.research.px_per_unit)
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, base.crosshair_id, None, protocol)
    baselines = []
    while assessment.status == AssessmentStatus.IN_PROGRESS:
        assessment, session = _complete(repo, protocol, assessment, snapshot=snapshot)
        if session.assessment_stage == AssessmentStage.EXPERIMENTAL:
            baselines.append(session)
    for record in (_candidate("A"), _candidate("B", color="#FF00FF", gap=4), _candidate("C", size=8)):
        repo.add_crosshair(record)
    result = score_candidates(repo, context.research, base, build_profile(repo, player.player_id))
    rec_id = store_recommendation(repo, result)
    return protocol, rec_id, baselines


def _start(context, candidate_rank: int = 1):
    protocol, rec_id, baselines = _baseline(context)
    rec = context.repository.get_recommendation(rec_id)
    chosen = rec["candidates"][candidate_rank - 1]["crosshair_id"]
    evaluation = start_evaluation(context.repository, protocol, context.current_player.player_id, rec_id, chosen)
    return protocol, evaluation, baselines


def _run_condition(context, protocol, evaluation):
    repo = context.repository
    evaluation = repo.get_condition_evaluation(evaluation.evaluation_id)
    assessment = start_or_resume_condition_assessment(repo, protocol, evaluation)
    record = repo.get_crosshair(assessment.crosshair_id)
    snapshot = crosshair_snapshot(record, context.research.px_per_unit)
    sessions = []
    while assessment.status == AssessmentStatus.IN_PROGRESS:
        assessment, session = _complete(repo, protocol, assessment, evaluation, snapshot)
        sessions.append(session)
    return repo.advance_condition_evaluation(evaluation.evaluation_id), sessions


def _run_all(context, protocol, evaluation):
    first = _run_condition(context, protocol, evaluation)
    second = _run_condition(context, protocol, evaluation)
    return second[0], first[1] + second[1]


def _evaluation_run(context, evaluation, assessment, stage):
    task = ExperimentType(assessment.current_task)
    crosshair = context.repository.get_crosshair(assessment.crosshair_id)
    return RunSetup(
        crosshair=crosshair, condition=assessment.condition, assessment_id=assessment.assessment_id,
        assessment_stage=stage, task_order_mode=TaskOrderMode.COUNTERBALANCED,
        task_order_group=assessment.task_order_group, task_order=tuple(assessment.order_for_stage(stage)),
        task_position=assessment.order_for_stage(stage).index(str(task)) + 1,
        **session_link(evaluation, assessment, task),
    )


def _run_flick_window(context, qapp, run: RunSetup, trials: int) -> tuple[int, str]:
    from app.ui.flick_window import FlickExperimentWindow, State

    window = FlickExperimentWindow(context, run)
    window.resize(1400, 1000)
    window.show()
    finished = []
    window.finished.connect(lambda sid, status: finished.append(sid))
    press_key(window, Qt.Key.Key_Space)
    for _ in range(trials):
        start_trial(window, qapp)
        target = window._current_target()
        point = QPointF(target.x, target.y)
        move(window, point)
        click(window, point)
    assert window.state == State.DONE
    done_text = window._done_text()
    window.close()
    return finished[0], done_text


# ------------------------------------------------------- 1-3 conditions
def test_baseline_condition_sessions(context) -> None:
    _, _, baselines = _baseline(context)
    assert len(baselines) == 3
    for session in baselines:
        assert session.condition == Condition.BASELINE
        assert session.condition_position is None and session.evaluation_id is None
        assert session.seed_group == "baseline"
    with pytest.raises(ValidationError):
        Session(player_id="P-TASK", experiment_type=ExperimentType.FLICK, condition=Condition.BASELINE,
                session_number=1, crosshair_id=1, condition_position=1).validate()


def test_standard_condition_sessions_repeat_baseline_crosshair(context) -> None:
    protocol, evaluation, baselines = _start(context)
    _, sessions = _run_all(context, protocol, evaluation)
    standard = [s for s in sessions if s.condition == Condition.STANDARD]
    assert len(standard) == 6  # familiarization + experimental for three tasks
    assert {s.crosshair_id for s in standard} == {baselines[0].crosshair_id}
    assert {s.seed_group for s in standard if s.assessment_stage == AssessmentStage.EXPERIMENTAL} == {"standard"}
    stored = context.repository.get_session(standard[-1].session_id)
    assert stored.condition == Condition.STANDARD


def test_candidate_condition_sessions_use_selected_candidate(context) -> None:
    protocol, evaluation, _ = _start(context)
    _, sessions = _run_all(context, protocol, evaluation)
    candidate = [s for s in sessions if s.condition == Condition.CANDIDATE]
    assert len(candidate) == 6
    assert {s.crosshair_id for s in candidate} == {evaluation.selected_candidate_id}
    assert {s.seed_group for s in candidate if s.assessment_stage == AssessmentStage.EXPERIMENTAL} == {"candidate"}


# --------------------------------------------------- 4-6 assignment/resume
def test_condition_order_assignment_is_deterministic_and_crossed_with_task_order() -> None:
    groups = [condition_order_for_sequence(i).group for i in range(1, 25)]
    assert groups == [condition_order_for_sequence(i).group for i in range(1, 25)]
    assert groups[:12] == ["CS", "SC", "CS", "SC", "CS", "SC", "SC", "CS", "SC", "CS", "SC", "CS"]
    for start in (1, 13):
        cells = Counter((assignment_for_sequence(i).group, condition_order_for_sequence(i).group)
                        for i in range(start, start + 12))
        assert len(cells) == 12 and set(cells.values()) == {1}  # every task order with CS and SC once
    assert condition_order_for_sequence(1).order == CONDITION_ORDER_GROUPS["CS"]
    assert condition_order_for_sequence(1).method == CONDITION_ASSIGNMENT_METHOD
    with pytest.raises(ValidationError):
        condition_order_for_sequence(0)


def test_condition_order_assignment_is_persisted_and_immutable(repo) -> None:
    first = repo.save_player(Player(player_id="P-COND-1"))
    second = repo.save_player(Player(player_id="P-COND-2"))
    assert (first.condition_order_group, second.condition_order_group) == ("CS", "SC")
    again = repo.save_player(Player(player_id="P-COND-1", mouse_dpi=1600))
    assert (again.condition_order_group, again.condition_order, again.condition_assignment_method) == (
        "CS", ("candidate", "standard"), CONDITION_ASSIGNMENT_METHOD)
    row = repo.db.connection.execute(
        "SELECT condition_order_group, condition_order_json, condition_assignment_method "
        "FROM players WHERE player_id = 'P-COND-2'").fetchone()
    assert (row[0], json.loads(row[1]), row[2]) == ("SC", ["standard", "candidate"], CONDITION_ASSIGNMENT_METHOD)
    with pytest.raises(sqlite3.IntegrityError):
        repo.db.connection.execute("UPDATE players SET condition_order_group = 'SC' WHERE player_id = 'P-COND-1'")
    with pytest.raises(RepositoryError):
        repo.save_player(Player(player_id="P-COND-1", condition_order_group="SC",
                                condition_order=("standard", "candidate")))


def test_resume_keeps_condition_order_and_assessment(context) -> None:
    protocol, evaluation, _ = _start(context)
    repo = context.repository
    first = start_or_resume_condition_assessment(repo, protocol, evaluation)
    first, _ = _complete(repo, protocol, first, evaluation)
    resumed = start_or_resume_condition_assessment(repo, protocol, repo.get_condition_evaluation(
        evaluation.evaluation_id))
    assert resumed.assessment_id == first.assessment_id
    assert resumed.condition == evaluation.current_condition
    assert (resumed.stage, resumed.current_position) == (first.stage, first.current_position)
    stored = repo.get_condition_evaluation(evaluation.evaluation_id)
    assert (stored.condition_order_group, stored.condition_order) == (
        evaluation.condition_order_group, evaluation.condition_order)
    with pytest.raises(sqlite3.IntegrityError):
        repo.db.connection.execute(
            "UPDATE condition_evaluations SET condition_order_group = 'SC', "
            "condition_order_json = '[\"standard\",\"candidate\"]' WHERE evaluation_id = ?",
            (evaluation.evaluation_id,))
    with pytest.raises(sqlite3.IntegrityError):
        repo.db.connection.execute("UPDATE sessions SET condition = 'baseline' WHERE evaluation_id = ?",
                                   (evaluation.evaluation_id,))


# ------------------------------------------------------ 7-9 profile/source
def test_profile_excludes_candidate_sessions(context) -> None:
    protocol, evaluation, baselines = _start(context)
    _run_all(context, protocol, evaluation)
    profile = build_profile(context.repository, context.current_player.player_id)
    candidate_ids = {s.session_id for s in context.repository.list_sessions(condition=Condition.CANDIDATE)}
    assert candidate_ids and not candidate_ids & set(profile.source_session_ids)


def test_profile_excludes_standard_sessions_and_uses_initial_baseline(context) -> None:
    protocol, evaluation, baselines = _start(context)
    _run_all(context, protocol, evaluation)
    repo = context.repository
    # A later baseline session must not replace the initial one.
    later = repo.create_session(Session(
        player_id=context.current_player.player_id, experiment_type=ExperimentType.FLICK,
        condition=Condition.BASELINE, session_number=repo.next_session_number(context.current_player.player_id),
        crosshair_id=baselines[0].crosshair_id))
    repo.finish_session(later.session_id, SessionStatus.COMPLETED)
    profile = build_profile(repo, context.current_player.player_id)
    standard_ids = {s.session_id for s in repo.list_sessions(condition=Condition.STANDARD)}
    assert standard_ids and not standard_ids & set(profile.source_session_ids)
    assert sorted(profile.source_session_ids) == sorted(s.session_id for s in baselines)
    assert PROFILE_RULE == "initial completed baseline session per task"


def test_recommendation_uses_initial_baseline_only(context) -> None:
    protocol, evaluation, baselines = _start(context)
    repo = context.repository
    rec = repo.get_recommendation(evaluation.recommendation_id)
    initial = {str(s.experiment_type): s for s in baselines}
    assert sorted(rec["source_session_ids"]) == sorted(s.session_id for s in baselines)
    assert recommendation_source_problems(repo, rec, initial) == []
    _, sessions = _run_condition(context, protocol, evaluation)
    tampered = dict(rec, source_session_ids=[sessions[-1].session_id, *rec["source_session_ids"][1:]])
    assert recommendation_source_problems(repo, tampered, initial)
    # A run whose sources are not the initial baselines cannot start a cycle.
    other_player = repo.save_player(Player(player_id="P-OTHER"))
    other_rec = repo.add_recommendation(other_player.player_id, "m", "v", {}, {}, [baselines[0].session_id],
                                        [{"crosshair_id": evaluation.selected_candidate_id, "rank": 1,
                                          "score": 0.5, "component_scores": {}, "explanation": "x"}])
    with pytest.raises(EvaluationError):
        start_evaluation(repo, protocol, other_player.player_id, other_rec, evaluation.selected_candidate_id)


# -------------------------------------------------------- 10-11 selection
def test_selected_candidate_stays_fixed(context) -> None:
    protocol, evaluation, _ = _start(context)
    repo = context.repository
    rec = repo.get_recommendation(evaluation.recommendation_id)
    other = next(c["crosshair_id"] for c in rec["candidates"]
                 if c["crosshair_id"] != evaluation.selected_candidate_id)
    assert [c["crosshair_id"] for c in rec["candidates"] if c["selected_by_player"]] == [
        evaluation.selected_candidate_id]
    with pytest.raises(RepositoryError):
        repo.mark_candidate_selected(evaluation.recommendation_id, other)
    with pytest.raises(RepositoryError):
        start_evaluation(repo, protocol, context.current_player.player_id, evaluation.recommendation_id, other)
    with pytest.raises(sqlite3.IntegrityError):
        repo.db.connection.execute("UPDATE condition_evaluations SET selected_candidate_id = ? "
                                   "WHERE evaluation_id = ?", (other, evaluation.evaluation_id))
    assert repo.get_condition_evaluation(evaluation.evaluation_id).selected_candidate_id == \
        evaluation.selected_candidate_id


def test_standard_uses_baseline_snapshot_not_current_configuration(context) -> None:
    protocol, evaluation, baselines = _start(context)
    repo = context.repository
    assert evaluation.standard_crosshair_snapshot == baselines[0].crosshair_snapshot
    assert evaluation.standard_crosshair_id == baselines[0].crosshair_id
    changed = repo.add_crosshair(CrosshairRecord(
        name="New standard", role=CrosshairRole.BASELINE, color="#FFFF00", size=6, thickness=2, gap=3,
        outline_enabled=True, outline_thickness=1, opacity=1.0))
    context.baseline_crosshair = changed  # configuration file changed after the baseline
    differences = current_standard_differences(changed, context.research.px_per_unit,
                                               evaluation.standard_crosshair_snapshot)
    assert "color" in differences
    assert condition_crosshair(repo, evaluation, Condition.STANDARD).crosshair_id == baselines[0].crosshair_id


# ------------------------------------------------------ 12-13 seeds/plans
def test_each_condition_uses_a_different_seed() -> None:
    research = load_research_parameters()
    protocol = build_protocol(research)
    for task in ("flick", "tracking", "switching"):
        baseline_seed = research.task_parameters(task)["random_seed"]
        seeds = {protocol.experimental_seed(c, task, baseline_seed) for c in ("baseline", "standard", "candidate")}
        assert len(seeds) == 3
        assert protocol.experimental_seed("baseline", task, baseline_seed) == baseline_seed
    snapshot = protocol.stored_snapshot()["condition_design"]
    assert set(snapshot["random_seed"]) == {"standard", "candidate"}
    research.protocol["condition_random_seed"]["candidate"]["flick"] = \
        research.protocol["condition_random_seed"]["standard"]["flick"]
    with pytest.raises(ValidationError):
        build_protocol(research)


def test_condition_seeds_keep_parameter_distributions() -> None:
    research = load_research_parameters()
    protocol = build_protocol(research)
    config = FlickConfig.from_dict(research.flick_task)
    plans = {c: generate_plan(config, 1400, 1000, protocol.experimental_seed(c, "flick", config.random_seed))
             for c in ("baseline", "standard", "candidate")}
    distances = {c: sorted(t.planned_distance_px for t in plan) for c, plan in plans.items()}
    assert distances["baseline"] == distances["standard"] == distances["candidate"]
    assert len({tuple((t.x, t.y) for t in plan) for plan in plans.values()}) == 3


# ------------------------------------------------------ 14 familiarization
def test_familiarization_is_recorded_but_excluded(context, qapp) -> None:
    context.research.flick_task.update(trial_count=2)
    context.research.protocol["condition_familiarization_trial_count"]["flick"] = 1
    protocol, evaluation, baselines = _start(context)
    repo = context.repository
    assessment = start_or_resume_condition_assessment(repo, protocol, evaluation)
    assert assessment.stage == AssessmentStage.FAMILIARIZATION
    while assessment.current_task != ExperimentType.FLICK:
        assessment, _ = _complete(repo, protocol, assessment, evaluation)
    run = _evaluation_run(context, evaluation, assessment, AssessmentStage.FAMILIARIZATION)
    session_id, done_text = _run_flick_window(context, qapp, run, trials=1)
    session = repo.get_session(session_id)
    assert session.assessment_stage == AssessmentStage.FAMILIARIZATION
    assert session.seed_group == "familiarization"
    assert session.random_seed == protocol.pre_block_seed("familiarization", "flick")
    trials = repo.list_trials(session_id)
    assert trials and {t.trial_phase for t in trials} == {TrialPhase.PRACTICE}  # raw data kept
    assert analyze_session(repo, session_id, store=False).metrics["trials"] == 0
    assert "Familiarization complete" in done_text
    assert session_id not in build_profile(repo, context.current_player.player_id).source_session_ids
    assert all(s.session_id != session_id
               for by_task in evaluation_sessions(repo, evaluation).values() for s in by_task.values())
    # Disabled familiarization starts directly with the experimental block.
    context.research.protocol["condition_familiarization_enabled"] = False
    assert build_protocol(context.research).pre_block_count("familiarization", "flick") == 0


# ------------------------------------------------------- 15 comparison
def test_three_condition_comparison_is_descriptive() -> None:
    m = MetricComparison("completion_time_median_ms", 500.0, 479.0, other_label="candidate")
    assert m.summary_text("Standard", "Candidate") == "Candidate condition was 4.2% lower than Standard condition."
    rate = MetricComparison("hit_rate", 0.5, 0.6, other_label="standard")
    assert rate.summary_text("Baseline", "Standard") == "Standard condition was 10.0 pp higher than Baseline condition."
    assert rate.direction_text() == "higher with standard"
    assert MetricComparison("hit_rate", None, 0.6).summary_text("Baseline", "Candidate").startswith("No data")


def test_three_condition_comparison_of_an_evaluation(context) -> None:
    protocol, evaluation, baselines = _start(context)
    _run_all(context, protocol, evaluation)
    comparisons = compare_evaluation(context.repository, evaluation.evaluation_id)
    assert [c.task for c in comparisons] == list(ExperimentType)
    comp = compare_conditions(context.repository, evaluation.evaluation_id, ExperimentType.FLICK)
    assert [(str(p.reference_condition), str(p.compared_condition)) for p in comp.pairs] == [
        ("baseline", "standard"), ("baseline", "candidate"), ("standard", "candidate")]
    assert comp.analyses[Condition.BASELINE].session.session_id == \
        evaluation.initial_baseline_sessions["flick"]
    assert all(a is not None for a in comp.analyses.values())
    assert any("order effect" in c for c in comp.caveats)
    assert any("not claimed to be equivalent" in c for c in comp.caveats)
    assert any("No statistical test" in c for c in comp.caveats)
    rows = comp.csv_rows()
    assert rows and all(len(row) == len(CONDITION_CSV_HEADER) for row in rows)
    text = " ".join(comp.caveats) + " ".join(str(row[-1]) for row in rows)
    assert not FORBIDDEN_WORDS.search(text)


# ------------------------------------------------ 16-17 linking / export
def test_condition_session_linking_and_export_metadata(context, qapp, tmp_path) -> None:
    context.research.flick_task.update(trial_count=2)
    context.research.protocol["condition_familiarization_enabled"] = False
    protocol, evaluation, baselines = _start(context)
    repo = context.repository
    assessment = start_or_resume_condition_assessment(repo, protocol, evaluation)
    assert assessment.stage == AssessmentStage.EXPERIMENTAL
    while assessment.current_task != ExperimentType.FLICK:
        assessment, _ = _complete(repo, protocol, assessment, evaluation)
    run = _evaluation_run(context, evaluation, assessment, AssessmentStage.EXPERIMENTAL)
    session_id, done_text = _run_flick_window(context, qapp, run, trials=2)
    session = repo.get_session(session_id)
    condition = evaluation.current_condition
    initial_flick = evaluation.initial_baseline_sessions["flick"]
    assert session.condition == condition
    assert session.evaluation_id == evaluation.evaluation_id
    assert session.initial_baseline_session_id == initial_flick == session.parent_session_id
    assert (session.condition_order_group, session.condition_order, session.condition_position) == (
        evaluation.condition_order_group, tuple(evaluation.condition_order), 1)
    assert session.recommendation_id == evaluation.recommendation_id
    assert session.selected_candidate_id == evaluation.selected_candidate_id
    assert session.protocol_version == protocol.version and session.crosshair_snapshot
    assert session.random_seed == protocol.experimental_seed(str(condition), "flick", 0)
    assert session.seed_group == str(condition)
    assert "hits" not in done_text  # no performance shown before the next condition

    folder = export_session(repo, analyze_session(repo, session_id, store=False), tmp_path)
    with (folder / "trials.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert set(SESSION_ORDER_COLUMNS + CONDITION_COLUMNS) <= set(row)
    assert (row["participant_id"], row["task"], row["condition"], row["condition_position"],
            row["condition_order_group"], row["seed"], row["crosshair_id"]) == (
        session.player_id, "flick", str(condition), "1", evaluation.condition_order_group,
        str(session.random_seed), str(session.crosshair_id))
    assert row["trial_id"] and row["protocol_version"] == protocol.version
    payload = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert payload["condition_metadata"]["evaluation_id"] == evaluation.evaluation_id
    assert payload["condition_metadata"]["initial_baseline_session_id"] == initial_flick


def test_participant_facing_evaluation_text_is_neutral(context) -> None:
    from app.ui.aim_selection_page import AimSelectionPage

    context.research.protocol["debug_task_selection_enabled"] = False
    _, evaluation, _ = _start(context)
    page = AimSelectionPage(context)
    page.on_page_shown()
    text = page.assessment_status.text()
    assert "Next assessment: Crosshair evaluation" in text
    for hidden in ("CS", "SC", "candidate", "standard", "Candidate", "Standard"):
        assert hidden not in text
    assert page.controlled_button.isEnabled()


def test_ui_selection_fixes_candidate_and_launches_evaluation(context) -> None:
    from app.ui.aim_selection_page import AimSelectionPage
    from app.ui.recommendation_page import RecommendationPage

    protocol, rec_id, baselines = _baseline(context)
    repo = context.repository
    page = RecommendationPage(context)
    page.on_page_shown()
    chosen = page.recommendation["candidates"][1]["crosshair_id"]
    evaluation = page.select_for_evaluation(chosen, confirm=False)
    assert evaluation is not None and evaluation.selected_candidate_id == chosen
    assert page.select_for_evaluation(page.recommendation["candidates"][0]["crosshair_id"], confirm=False) is None
    page.generate()  # once per cycle: no new recommendation run
    assert len(repo.list_recommendations(context.current_player.player_id)) == 1

    aim = AimSelectionPage(context)
    aim.on_page_shown()
    captured = {}
    aim._open_task_window = lambda task, run, controlled: captured.update(task=task, run=run, controlled=controlled)
    aim.start_or_resume_assessment()
    run = captured["run"]
    assert captured["controlled"] is True
    assert run.evaluation_id == evaluation.evaluation_id and run.condition == evaluation.current_condition
    assert run.assessment_stage == AssessmentStage.FAMILIARIZATION and run.participant_neutral
    assert run.initial_baseline_session_id == evaluation.initial_baseline_sessions[str(captured["task"])]


def test_rest_before_second_condition_is_configurable(context) -> None:
    from app.ui.aim_selection_page import AimSelectionPage

    context.research.protocol["condition_rest_seconds"] = 3600
    protocol, evaluation, _ = _start(context)
    evaluation, _ = _run_condition(context, protocol, evaluation)
    assert evaluation.current_position == 2
    page = AimSelectionPage(context)
    page.on_page_shown()
    assert page.rest_remaining_seconds(evaluation) > 0
    assert not page.controlled_button.isEnabled()
    context.research.protocol["condition_rest_seconds"] = 0
    assert page.rest_remaining_seconds(evaluation) == 0


# ------------------------------------------------ 18-20 history/migration
def _schema5_database(path, monkeypatch):
    later = {v: sql for v, sql in database_module.MIGRATIONS.items() if v >= 6}
    for version in later:
        monkeypatch.delitem(database_module.MIGRATIONS, version)
    old = Database(path).open()
    assert old.schema_version() == "5"
    conn = old.connection
    conn.execute("INSERT INTO players(player_id, created_at, updated_at) VALUES ('P-HIST', '2026-01-01', '2026-01-01')")
    conn.execute(
        """INSERT INTO crosshairs(name, role, color, size, thickness, gap,
               outline_enabled, outline_thickness, opacity, config_hash, created_at)
           VALUES ('Historical', 'baseline', '#FFFFFF', 6, 2, 3, 1, 1, 1, 'hash', '2026-01-01')""")
    for number, condition in ((1, "baseline"), (2, "candidate")):
        conn.execute(
            """INSERT INTO sessions(player_id, started_at, experiment_type, condition,
                   session_number, status, crosshair_id, random_seed)
               VALUES ('P-HIST', '2026-01-0' || ?, 'flick', ?, ?, 'completed', 1, 20261003)""",
            (number, condition, number))
    conn.execute(
        """INSERT INTO trials(session_id, trial_number, recorded_at, task_type, result,
               trial_status, trial_phase)
           VALUES (1, 1, '2026-01-01', 'flick', 'hit', 'valid', 'experimental')""")
    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("players", "sessions", "trials")}
    old.close()
    return later, counts


def test_historical_sessions_keep_unknown_condition_metadata(tmp_path, monkeypatch) -> None:
    later, _ = _schema5_database(tmp_path / "app.db", monkeypatch)
    for version, sql in later.items():
        monkeypatch.setitem(database_module.MIGRATIONS, version, sql)
    migrated = Database(tmp_path / "app.db").open()
    repo = Repository(migrated)
    for session_id in (1, 2):
        session = repo.get_session(session_id)
        assert (session.evaluation_id, session.condition_order_group, session.condition_order,
                session.condition_position, session.initial_baseline_session_id,
                session.selected_candidate_id, session.seed_group) == (None,) * 7
    assert repo.get_session(2).condition == Condition.CANDIDATE
    assert repo.get_player("P-HIST").condition_order_group is None  # not inferred during migration
    folder = export_session(repo, analyze_session(repo, 1, store=False), tmp_path / "exports")
    with (folder / "trials.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["condition_position"] == "" and row["condition_order_group"] == "" and row["seed_group"] == ""
    migrated.close()


def test_protocol_version_compatibility(repo, player, crosshair) -> None:
    protocol = build_protocol(load_research_parameters())
    assert PROTOCOL_SCHEMA == "protocol-3"
    snapshot = protocol.stored_snapshot()
    assert snapshot["condition_design"]["familiarization"]["trial_count"] == {
        "flick": 3, "tracking": 1, "switching": 1}
    # Baseline assessments still use the practice block, read from the stored snapshot.
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol)
    assert assessment.stage == AssessmentStage.PRACTICE
    # A session stored under an older protocol snapshot (no condition_design) still loads and validates.
    old = repo.create_session(Session(
        player_id=player.player_id, experiment_type=ExperimentType.FLICK, condition=Condition.BASELINE,
        session_number=repo.next_session_number(player.player_id), crosshair_id=crosshair.crosshair_id,
        protocol_version="pilot-placeholder+old", protocol_snapshot={"schema": "protocol-2"}))
    assert repo.get_session(old.session_id).protocol_snapshot == {"schema": "protocol-2"}


def test_migration_backs_up_and_preserves_data(tmp_path, monkeypatch) -> None:
    path = tmp_path / "app.db"
    later, counts = _schema5_database(path, monkeypatch)
    # A failing migration rolls back completely and leaves schema 5 data untouched.
    monkeypatch.setitem(database_module.MIGRATIONS, 6, later[6] + "\nSELECT * FROM no_such_table;\n")
    with pytest.raises(DatabaseError):
        Database(path).open()
    check = sqlite3.connect(str(path))
    assert check.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()[0] == "5"
    assert check.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == counts["sessions"]
    check.close()

    for version, sql in later.items():
        monkeypatch.setitem(database_module.MIGRATIONS, version, sql)
    migrated = Database(path).open()
    assert migrated.schema_version() == str(max(later))
    conn = migrated.connection
    assert {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in counts} == counts
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    backups = list((tmp_path / "backups").glob("app_schema5_*.db"))
    assert backups
    backup = sqlite3.connect(str(backups[0]))
    assert backup.execute("SELECT COUNT(*) FROM trials").fetchone()[0] == counts["trials"]
    backup.close()
    repo = Repository(migrated)
    new = repo.create_session(Session(player_id="P-HIST", experiment_type=ExperimentType.TRACKING,
                                      condition=Condition.STANDARD, session_number=3, crosshair_id=1))
    assert new.session_id == 3  # autoincrement sequence preserved
    assert path.exists()
    migrated.close()
