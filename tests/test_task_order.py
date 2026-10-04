"""Deterministic task-order assignment, sequencing, recovery and export (Phase 4)."""

from __future__ import annotations

import csv
import itertools
import json
import sqlite3

import pytest
from PySide6.QtCore import QPointF, Qt

from app.analysis.export import SESSION_ORDER_COLUMNS, export_session
from app.analysis.metrics import analyze_session
from app.analysis.profile import build_profile
from app.config.research import load_research_parameters
from app.data import database as database_module
from app.data.database import Database
from app.data.models import (
    AssessmentStage,
    AssessmentStatus,
    Condition,
    ExperimentType,
    Player,
    Session,
    SessionStatus,
    TaskAssessment,
    TaskOrderMode,
)
from app.data.repository import Repository
from app.experiment.protocol import build_protocol
from app.experiment.task_order import (
    ASSIGNMENT_METHOD,
    TASK_ORDER_GROUPS,
    TASK_ORDER_METHOD,
    assignment_for_sequence,
)
from app.ui.experiment_window import RunSetup
from experiment_helpers import click, move, press_key, start_trial


def _complete_current(repo: Repository, assessment: TaskAssessment) -> tuple[TaskAssessment, Session]:
    """Store and complete the current task without generating trial data."""
    order = assessment.order_for_stage()
    session = repo.create_session(Session(
        player_id=assessment.player_id,
        experiment_type=assessment.current_task,
        condition=assessment.condition,
        session_number=repo.next_session_number(assessment.player_id),
        crosshair_id=assessment.crosshair_id,
        recommendation_id=assessment.recommendation_id,
        assessment_id=assessment.assessment_id,
        assessment_stage=assessment.stage,
        task_order_mode=TaskOrderMode.COUNTERBALANCED,
        task_order_group=assessment.task_order_group,
        task_order=order,
        task_position=assessment.current_position,
        protocol_version=assessment.protocol_version,
        protocol_snapshot=assessment.protocol_snapshot,
    ))
    repo.finish_session(session.session_id, SessionStatus.COMPLETED)
    session = repo.get_session(session.session_id)
    return repo.complete_task_assessment_session(assessment.assessment_id, session.session_id), session


def _run_flick(context, qapp) -> int:
    from app.ui.flick_window import FlickExperimentWindow

    context.research.protocol["practice_enabled"] = False
    context.research.flick_task["trial_count"] = 1
    window = FlickExperimentWindow(context)
    window.resize(1200, 800)
    window.show()
    press_key(window, Qt.Key.Key_Space)
    start_trial(window, qapp)
    target = window._current_target()
    point = QPointF(target.x, target.y)
    move(window, point)
    click(window, point)
    session_id = window.session.session_id
    window.close()
    return session_id


# -------------------------------------------------------------- six groups
def test_all_six_task_order_permutations_exist() -> None:
    expected = set(itertools.permutations(ExperimentType))
    assert list(TASK_ORDER_GROUPS) == ["FTS", "FST", "TFS", "TSF", "SFT", "STF"]
    assert set(TASK_ORDER_GROUPS.values()) == expected


def test_sequence_assignment_is_deterministic_and_rotates() -> None:
    first_cycle = [assignment_for_sequence(i).group for i in range(1, 7)]
    second_cycle = [assignment_for_sequence(i).group for i in range(7, 13)]
    assert first_cycle == list(TASK_ORDER_GROUPS)
    assert second_cycle == first_cycle
    assert assignment_for_sequence(4) == assignment_for_sequence(4)


def test_same_participant_keeps_stored_assignment(repo: Repository) -> None:
    first = repo.save_player(Player(player_id="P-SAME", mouse_dpi=800))
    updated = repo.save_player(Player(player_id="P-SAME", mouse_dpi=1600))
    assert (updated.task_order_sequence, updated.task_order_group, updated.task_order) == (
        first.task_order_sequence, first.task_order_group, first.task_order,
    )
    assert repo.get_player("P-SAME").task_order == first.task_order
    with pytest.raises(sqlite3.IntegrityError):
        repo.db.connection.execute(
            "UPDATE players SET task_order_group = 'STF' WHERE player_id = 'P-SAME'"
        )


def test_participant_sequence_assigns_different_groups_and_stores_order(repo: Repository) -> None:
    participants = [repo.save_player(Player(player_id=f"P-{i}")) for i in range(1, 7)]
    assert [p.task_order_group for p in participants] == list(TASK_ORDER_GROUPS)
    assert len({p.task_order for p in participants}) == 6
    row = repo.db.connection.execute(
        "SELECT task_order_sequence, task_order_group, task_order_json FROM players WHERE player_id = 'P-3'"
    ).fetchone()
    assert row["task_order_sequence"] == 3
    assert row["task_order_group"] == "TFS"
    assert tuple(json.loads(row["task_order_json"])) == participants[2].task_order


# ----------------------------------------------------------- protocol/order
def test_protocol_records_counterbalancing_method() -> None:
    protocol = build_protocol(load_research_parameters())
    snapshot = protocol.stored_snapshot()
    assert snapshot["task_order_method"] == TASK_ORDER_METHOD
    assert snapshot["assignment_method"] == ASSIGNMENT_METHOD
    assert snapshot["available_task_orders"] == list(TASK_ORDER_GROUPS)
    assert snapshot["practice"]["task_order_method"] == "match_assigned"


def test_practice_uses_assigned_order_by_default(repo, player, crosshair) -> None:
    protocol = build_protocol(load_research_parameters())
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol,
    )
    assert assessment.practice_task_order == player.task_order
    assert assessment.task_order == player.task_order
    assert assessment.current_task == ExperimentType(player.task_order[0])


def test_fixed_practice_order_is_configurable_but_does_not_change_assignment(repo, crosshair) -> None:
    research = load_research_parameters()
    research.protocol["practice_task_order_method"] = "fixed"
    research.protocol["practice_fixed_task_order"] = ["switching", "tracking", "flick"]
    protocol = build_protocol(research)
    player = repo.save_player(Player(player_id="P-FIXED-PRACTICE"))
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol,
    )
    assert assessment.practice_task_order == ("switching", "tracking", "flick")
    assert assessment.task_order == player.task_order
    assert assessment.task_order_group == player.task_order_group


def test_controlled_assessment_progresses_practice_then_assessment_in_stored_order(
    repo, player, crosshair,
) -> None:
    protocol = build_protocol(load_research_parameters())
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol,
    )
    practice_seen, experimental_seen, sessions = [], [], []
    while assessment.status == AssessmentStatus.IN_PROGRESS:
        if assessment.stage == AssessmentStage.PRACTICE:
            practice_seen.append(str(assessment.current_task))
        else:
            experimental_seen.append(str(assessment.current_task))
        assessment, session = _complete_current(repo, assessment)
        sessions.append(session)

    assert practice_seen == list(player.task_order)
    assert experimental_seen == list(player.task_order)
    assert assessment.completed_tasks == {
        "practice": list(player.task_order),
        "experimental": list(player.task_order),
    }
    assert assessment.status == AssessmentStatus.COMPLETED
    assert [s.task_position for s in sessions[:3]] == [1, 2, 3]
    assert [s.task_position for s in sessions[3:]] == [1, 2, 3]
    assert all(s.task_order_group == player.task_order_group for s in sessions)


def test_completed_practice_only_session_never_becomes_profile_source(repo, player, crosshair) -> None:
    protocol = build_protocol(load_research_parameters())
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol,
    )
    assessment, practice_session = _complete_current(repo, assessment)
    assert practice_session.assessment_stage == AssessmentStage.PRACTICE
    assert build_profile(repo, player.player_id).source_session_ids == []


# ------------------------------------------------------- session and resume
def test_experiment_session_stores_participant_order(context, qapp) -> None:
    session = context.repository.get_session(_run_flick(context, qapp))
    player = context.current_player
    assert session.task_order_group == player.task_order_group
    assert session.task_order == player.task_order
    assert session.task_position == player.task_order.index("flick") + 1
    assert session.task_order_mode == TaskOrderMode.INDIVIDUAL
    assert session.assessment_stage == AssessmentStage.COMBINED


def test_resume_keeps_assessment_id_order_and_position_and_aborts_orphan(
    repo, player, crosshair,
) -> None:
    protocol = build_protocol(load_research_parameters())
    assessment = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol,
    )
    order = assessment.order_for_stage()
    orphan = repo.create_session(Session(
        player_id=player.player_id,
        experiment_type=assessment.current_task,
        condition=Condition.BASELINE,
        session_number=1,
        crosshair_id=crosshair.crosshair_id,
        assessment_id=assessment.assessment_id,
        assessment_stage=assessment.stage,
        task_order_mode=TaskOrderMode.COUNTERBALANCED,
        task_order_group=assessment.task_order_group,
        task_order=order,
        task_position=assessment.current_position,
    ))
    resumed = repo.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, crosshair.crosshair_id, None, protocol,
    )
    assert resumed.assessment_id == assessment.assessment_id
    assert resumed.task_order == assessment.task_order
    assert resumed.task_order_group == assessment.task_order_group
    assert resumed.current_position == assessment.current_position
    assert repo.get_session(orphan.session_id).status == SessionStatus.ABORTED


def test_debug_fixed_order_never_replaces_experimental_assignment(context) -> None:
    from app.ui.aim_selection_page import AimSelectionPage

    player_order = context.current_player.task_order
    context.research.protocol["debug_task_selection_enabled"] = True
    context.research.protocol["debug_fixed_task_order"] = ["switching", "tracking", "flick"]
    page = AimSelectionPage(context)
    page.on_page_shown()
    captured = {}
    page._open_task_window = lambda task, run, controlled: captured.update(
        task=task, run=run, controlled=controlled
    )
    page.start_task(ExperimentType.SWITCHING)
    assert captured["run"].task_order_mode == TaskOrderMode.DEBUG_FIXED
    assert captured["run"].task_order == ("switching", "tracking", "flick")
    assert captured["run"].task_order_group == "DEBUG"
    assert captured["controlled"] is False
    assert context.repository.get_player(context.current_player.player_id).task_order == player_order


def test_participant_facing_status_hides_group_when_debug_mode_is_off(context) -> None:
    from app.ui.aim_selection_page import AimSelectionPage

    context.research.protocol["debug_task_selection_enabled"] = False
    page = AimSelectionPage(context)
    page.on_page_shown()
    assert page.debug_card.isHidden()
    assert context.current_player.task_order_group not in page.assessment_status.text()
    assert "stored counterbalanced order" in page.assessment_status.text()


def test_participant_transition_names_only_next_task(context) -> None:
    from app.ui.aim_selection_page import AimSelectionPage

    context.research.protocol["practice_enabled"] = True
    protocol = build_protocol(context.research)
    player = context.current_player
    context.repository.start_or_resume_task_assessment(
        player.player_id, Condition.BASELINE, context.baseline_crosshair.crosshair_id, None, protocol,
    )
    page = AimSelectionPage(context)
    page.on_page_shown()
    assert page.assessment_status.text() == "Next practice:\nFlick Aim"
    assert player.task_order_group not in page.assessment_status.text()


# ------------------------------------------------------------------- export
def test_export_contains_task_order_metadata(context, qapp, tmp_path) -> None:
    session_id = _run_flick(context, qapp)
    analysis = analyze_session(context.repository, session_id, store=False)
    folder = export_session(context.repository, analysis, tmp_path)
    with (folder / "trials.csv").open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert set(SESSION_ORDER_COLUMNS) <= set(row)
    assert row["participant_id"] == context.current_player.player_id
    assert int(row["session_id"]) == session_id
    assert row["task_order_group"] == context.current_player.task_order_group
    assert tuple(json.loads(row["task_order"])) == context.current_player.task_order
    assert int(row["task_position"]) == context.current_player.task_order.index("flick") + 1
    for name in ("samples.csv", "events.csv"):
        with (folder / name).open(encoding="utf-8", newline="") as handle:
            exported = next(csv.DictReader(handle))
        assert set(SESSION_ORDER_COLUMNS) <= set(exported)
        assert exported["task_order_group"] == context.current_player.task_order_group
    payload = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    assert payload["task_order_metadata"]["participant_id"] == context.current_player.player_id
    assert payload["task_order_metadata"]["task_order_group"] == context.current_player.task_order_group


# ---------------------------------------------------------------- migration
def test_migration_5_preserves_historical_sessions_and_raw_trials(tmp_path, monkeypatch) -> None:
    path = tmp_path / "schema4.db"
    migration_5 = database_module.MIGRATIONS[5]
    monkeypatch.delitem(database_module.MIGRATIONS, 5)
    old = Database(path).open()
    assert old.schema_version() == "4"
    old.connection.execute(
        """INSERT INTO players(player_id, created_at, updated_at)
           VALUES ('P-HIST', '2026-01-01', '2026-01-01')"""
    )
    old.connection.execute(
        """INSERT INTO crosshairs(name, role, color, size, thickness, gap,
               outline_enabled, outline_thickness, opacity, config_hash, created_at)
           VALUES ('Historical', 'baseline', '#FFFFFF', 6, 2, 3, 1, 1, 1, 'hash', '2026-01-01')"""
    )
    old.connection.execute(
        """INSERT INTO sessions(player_id, started_at, experiment_type, condition,
               session_number, status, crosshair_id)
           VALUES ('P-HIST', '2026-01-01', 'flick', 'baseline', 1, 'completed', 1)"""
    )
    old.connection.execute(
        """INSERT INTO trials(session_id, trial_number, recorded_at, task_type, result,
               trial_status, trial_phase)
           VALUES (1, 1, '2026-01-01', 'flick', 'hit', 'valid', 'experimental')"""
    )
    old.connection.commit()
    old.close()

    monkeypatch.setitem(database_module.MIGRATIONS, 5, migration_5)
    migrated = Database(path).open()
    repo = Repository(migrated)
    assert migrated.schema_version() == "5"
    assert len(repo.list_trials(1)) == 1
    historical = repo.get_session(1)
    assert historical.task_order_group is None
    assert historical.task_order is None and historical.task_position is None
    assigned = repo.get_player("P-HIST")
    assert assigned.task_order_group == "FTS"
    assert assigned.task_order == ("flick", "tracking", "switching")
    migrated.close()
    assert list((tmp_path / "backups").glob("schema4_schema4_*.db"))
