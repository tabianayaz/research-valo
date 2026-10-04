"""Stabilisation, pre-target movement invalidation, timing fallback and per-metric validity."""

from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtCore import QPointF, Qt

from app.analysis.metrics import ANALYSIS_VERSION, TrialRow, analyze_session, compute_metrics, effective_status
from app.data import database as database_module
from app.data.database import Database
from app.data.models import (
    ExperimentType,
    TimingQuality,
    Trial,
    TrialEvent,
    TrialPhase,
    TrialResult,
    TrialSample,
    TrialStatus,
)
from app.experiment.common import EventType
from app.experiment.pointing import compute_pointing_measures, movement_reference
from app.experiment.timing import COMMON_TIMING_DEFINITION, ONSET_FALLBACK_MS, timing_definition
from app.ui.experiment_window import State
from experiment_helpers import begin_foreperiod, click, move, press_key, show_target, start_trial


def _window(context, kind: str = "flick", trial_count: int = 2):
    from app.ui.flick_window import FlickExperimentWindow
    from app.ui.switching_window import SwitchingExperimentWindow
    from app.ui.tracking_window import TrackingExperimentWindow

    getattr(context.research, f"{kind}_task").update(trial_count=trial_count)
    window_class = {"flick": FlickExperimentWindow, "tracking": TrackingExperimentWindow,
                    "switching": SwitchingExperimentWindow}[kind]
    window = window_class(context)
    window.resize(1400, 1000)
    window.show()
    press_key(window, Qt.Key.Key_Space)
    return window


def _offset(window, dx: float, dy: float = 0.0) -> QPointF:
    center = window._center_px()
    return QPointF(center.x() + dx, center.y() + dy)


# ------------------------------------------------------------ stabilisation
def test_start_click_enters_stabilization_not_foreperiod(context) -> None:
    window = _window(context)
    center = window._center_px()
    move(window, center)
    click(window, center)
    assert window.state == State.STABILIZING
    assert window.stabilize_timer.isActive()
    assert not window.foreperiod_timer.isActive()
    window.close()


def test_movement_during_stabilization_restarts_it(context) -> None:
    window = _window(context)
    center = window._center_px()
    move(window, center)
    click(window, center)
    move(window, _offset(window, 1))  # below the movement threshold: no reset
    assert window.state == State.STABILIZING
    move(window, _offset(window, 6))  # inside the region but above the threshold
    move(window, _offset(window, 40))  # outside the region
    assert window.state == State.STABILIZING
    kinds = [kind for _, kind, _, _ in window.recorder._events]
    assert kinds.count(EventType.STABILIZATION_RESET) == 2
    assert not window.stabilize_timer.isActive()
    window._on_stable()  # a stale timer callback must not start the foreperiod while outside the region
    assert window.state == State.STABILIZING
    window.close()


# --------------------------------------------------- pre-target movement
@pytest.mark.parametrize("kind", ["flick", "tracking", "switching"])
def test_pre_target_movement_invalidates_and_repeats_trial(context, qapp, kind) -> None:
    window = _window(context, kind)
    begin_foreperiod(window)
    plan_index = window.trial_index
    move(window, _offset(window, 8))
    assert window.state == State.WAIT_START
    assert window.trial_index == plan_index
    assert window.invalid_trials == 1
    assert window.results == []

    repo = context.repository
    session_id = window.session.session_id
    [invalid] = repo.list_trials(session_id)
    assert invalid.trial_status == TrialStatus.INVALID_PRE_MOVEMENT
    assert invalid.timing_quality == TimingQuality.NOT_APPLICABLE
    assert invalid.result == TrialResult.INCOMPLETE
    assert invalid.reaction_time_ms is None
    assert invalid.extra["plan_index"] == plan_index
    assert invalid.target_id is not None
    events = [e.event_type for e in repo.list_events(invalid.trial_id)]
    assert EventType.STABLE in events and events[-1] == EventType.PRE_TARGET_MOVEMENT
    assert EventType.TARGET_ONSET not in events
    assert repo.list_samples(invalid.trial_id), "raw samples of invalid trials are kept"

    start_trial(window, qapp)  # the same planned trial is presented again
    assert window.trial_index == plan_index
    window.close()


def test_invalid_trials_are_excluded_from_metrics_but_counted(context, qapp) -> None:
    window = _window(context, trial_count=2)
    begin_foreperiod(window)
    move(window, _offset(window, 30))  # left the region during the foreperiod
    for _ in range(2):
        start_trial(window, qapp)
        target = window._current_target()
        move(window, QPointF(target.x, target.y))
        click(window, QPointF(target.x, target.y))
    assert window.state == State.DONE
    analysis = analyze_session(context.repository, window.session.session_id, store=False)
    assert analysis.metrics["invalid_pre_movement_count"] == 1
    assert analysis.metrics["trials"] == 2
    assert analysis.metrics["hit_rate"] == 1.0
    assert analysis.mismatches == []
    window.close()


# ----------------------------------------------------------- timing fallback
def test_onset_fallback_is_flagged_and_excluded_from_time_measures(context, qapp) -> None:
    window = _window(context, trial_count=2)
    for fallback in (True, False):
        start_trial(window, qapp, fallback=fallback)
        target = window._current_target()
        move(window, QPointF(target.x, target.y))
        click(window, QPointF(target.x, target.y))
    trials = context.repository.list_trials(window.session.session_id)
    assert [t.trial_status for t in trials] == [TrialStatus.TIMING_FALLBACK, TrialStatus.VALID]
    assert [t.timing_quality for t in trials] == [TimingQuality.FALLBACK, TimingQuality.PAINT]
    assert all(t.trial_phase == TrialPhase.EXPERIMENTAL for t in trials)

    analysis = analyze_session(context.repository, window.session.session_id, store=False)
    assert analysis.metrics["timing_fallback_count"] == 1
    assert analysis.metrics["hit_rate"] == 1.0  # accuracy keeps fallback trials
    valid_row = analysis.rows[1]
    assert analysis.metrics["completion_time_median_ms"] == pytest.approx(valid_row.completion_time_ms)
    assert analysis.metrics["reaction_time_valid_trials"] <= 1
    window.close()


def test_switching_later_segments_use_previous_click_reference(context, qapp) -> None:
    window = _window(context, "switching", trial_count=1)
    start_trial(window, qapp)
    for target in window._trial().targets:
        move(window, QPointF(target.x, target.y))
        click(window, QPointF(target.x, target.y))
    trials = context.repository.list_trials(window.session.session_id)
    assert trials[0].timing_quality == TimingQuality.PAINT
    assert {t.timing_quality for t in trials[1:]} == {TimingQuality.PREVIOUS_CLICK}
    assert {t.trial_status for t in trials} == {TrialStatus.VALID}
    window.close()


# ------------------------------------------------------------ validity rules
def _row(status, result=TrialResult.HIT, moving=False, rt=200.0, phase=TrialPhase.EXPERIMENTAL, **extra) -> TrialRow:
    trial = Trial(session_id=1, trial_number=1, task_type=ExperimentType.FLICK, result=result,
                  trial_status=status, trial_phase=phase, extra=extra or None)
    return TrialRow(trial=trial, result=result, reaction_time_ms=rt, completion_time_ms=500.0,
                    error_distance=2.0, moving_at_onset=moving)


def test_per_metric_validity_flags() -> None:
    valid = _row(TrialStatus.VALID)
    assert valid.valid_for_reaction_time and valid.valid_for_completion_time and valid.valid_for_accuracy

    moving = _row(TrialStatus.VALID, moving=True)
    assert not moving.valid_for_reaction_time and moving.valid_for_completion_time

    fallback = _row(TrialStatus.TIMING_FALLBACK)
    assert not fallback.valid_for_reaction_time and not fallback.valid_for_completion_time
    assert fallback.valid_for_accuracy

    invalid = _row(TrialStatus.INVALID_PRE_MOVEMENT, result=TrialResult.INCOMPLETE, rt=None)
    assert invalid.excluded and not invalid.valid_for_accuracy

    practice = _row(TrialStatus.VALID, phase=TrialPhase.PRACTICE)
    assert practice.excluded and not practice.valid_for_reaction_time


def test_metrics_apply_validity_rules() -> None:
    rows = [_row(TrialStatus.VALID, rt=200.0), _row(TrialStatus.VALID, rt=900.0, moving=True),
            _row(TrialStatus.TIMING_FALLBACK, rt=50.0),
            _row(TrialStatus.INVALID_PRE_MOVEMENT, result=TrialResult.INCOMPLETE, rt=None)]
    metrics = compute_metrics(ExperimentType.FLICK, rows)
    assert metrics["reaction_time_median_ms"] == 200.0
    assert metrics["reaction_time_valid_trials"] == 1
    assert metrics["trials"] == 3
    assert metrics["timing_fallback_count"] == 1
    assert metrics["invalid_pre_movement_count"] == 1
    assert metrics["hit_rate"] == 1.0


def test_legacy_trials_derive_status_from_onset_flag() -> None:
    def legacy(**extra):
        return Trial(session_id=1, trial_number=1, task_type=ExperimentType.FLICK,
                     result=TrialResult.HIT, extra=extra)
    assert effective_status(legacy(onset_from_paint=True)) == TrialStatus.VALID
    assert effective_status(legacy(onset_from_paint=False)) == TrialStatus.TIMING_FALLBACK
    assert effective_status(legacy(onset_from_paint=False, is_switch=True)) == TrialStatus.VALID


def test_analysis_version_bumped() -> None:
    assert ANALYSIS_VERSION == "metrics-2"


# ------------------------------------------------------ movement reference
def test_movement_onset_is_measured_from_the_stable_position() -> None:
    events = [TrialEvent(-500, EventType.START_CLICK, 0, 0), TrialEvent(-300, EventType.STABLE, 0, 0),
              TrialEvent(0, EventType.TARGET_ONSET, 2, 0), TrialEvent(400, EventType.CLICK, 100, 0)]
    samples = [TrialSample(-300, 0, 0), TrialSample(0, 2, 0), TrialSample(100, 3, 0), TrialSample(200, 50, 0),
               TrialSample(400, 100, 0)]
    assert movement_reference(events, events[2]) == (0, 0)
    measures = compute_pointing_measures(samples, events, 100, 0, 40, 3)
    assert measures.reaction_time_ms == 100  # 3 px from the stable position, not from the onset position


# ------------------------------------------------------------------ timing
def test_timing_definitions_are_centralised() -> None:
    definition = timing_definition("flick-timing-2", extra="x")
    assert definition["version"] == "flick-timing-2"
    assert definition["extra"] == "x"
    for key in COMMON_TIMING_DEFINITION:
        assert key in definition
    assert ONSET_FALLBACK_MS == 50


# --------------------------------------------------------------- migration
def test_migration_3_adds_columns_and_backs_up_existing_data(tmp_path, monkeypatch) -> None:
    path = tmp_path / "old.db"
    later = {v: sql for v, sql in database_module.MIGRATIONS.items() if v >= 3}
    for version in later:
        monkeypatch.delitem(database_module.MIGRATIONS, version)
    old = Database(path).open()
    assert old.schema_version() == "2"
    old.connection.execute(
        "INSERT INTO players(player_id, created_at, updated_at) VALUES ('P-OLD', '2026-01-01', '2026-01-01')")
    old.connection.commit()
    old.close()

    for version, sql in later.items():
        monkeypatch.setitem(database_module.MIGRATIONS, version, sql)
    migrated = Database(path).open()
    assert migrated.schema_version() == str(max(later))
    columns = {row[1] for row in migrated.connection.execute("PRAGMA table_info(trials)")}
    assert {"trial_status", "timing_quality", "trial_phase"} <= columns
    assert [tuple(r) for r in migrated.connection.execute("SELECT player_id FROM players")] == [("P-OLD",)]
    migrated.close()

    [backup] = (tmp_path / "backups").glob("old_schema2_*.db")
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT player_id FROM players").fetchall() == [("P-OLD",)]
        assert "trial_status" not in {row[1] for row in conn.execute("PRAGMA table_info(trials)")}


def test_new_database_needs_no_backup(tmp_path) -> None:
    Database(tmp_path / "fresh.db").open().close()
    assert not (tmp_path / "backups").exists()


def test_status_check_constraint(repo, session) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo.db.connection.execute(
            "INSERT INTO trials(session_id, trial_number, task_type, result, trial_status) "
            "VALUES (?, 1, 'flick', 'hit', 'bogus')", (session.session_id,))
