"""Practice block, protocol versioning/snapshots and analysis exclusion rules (Phase 3)."""

from __future__ import annotations

import re
import sqlite3

import pytest
from PySide6.QtCore import QPointF, Qt

from app.analysis.comparison import compare_sessions
from app.analysis.metrics import analyze_session
from app.analysis.profile import build_profile
from app.config.research import load_research_parameters
from app.data.models import Condition, ExperimentType, SessionStatus, TrialPhase, TrialResult, TrialStatus
from app.experiment.protocol import build_protocol
from app.ui.experiment_window import PRACTICE_COMPLETE_TEXT, RunSetup, State
from app.utils.validators import ValidationError
from experiment_helpers import begin_foreperiod, click, move, press_key, start_trial


def _flick(context, run=None, practice: int = 0, trials: int = 2):
    from app.ui.flick_window import FlickExperimentWindow

    context.research.protocol["practice_enabled"] = practice > 0
    context.research.protocol["practice_trial_count"]["flick"] = practice
    context.research.flick_task.update(trial_count=trials)
    window = FlickExperimentWindow(context, run)
    window.resize(1400, 1000)
    window.show()
    return window


def _flick_trial(window, qapp, hit: bool = True) -> None:
    start_trial(window, qapp)
    target = window._current_target()
    point = QPointF(target.x, target.y) if hit else QPointF(target.x + 200, target.y + 200)
    move(window, point)
    click(window, point)


def _run_flick(context, qapp, run=None, practice: int = 0, trials: int = 2, abort: bool = False) -> int:
    window = _flick(context, run, practice, trials)
    press_key(window, Qt.Key.Key_Space)
    for _ in range(practice):
        _flick_trial(window, qapp, hit=False)
    if practice:
        press_key(window, Qt.Key.Key_Space)
    for i in range(trials):
        if abort and i == trials - 1:
            break
        _flick_trial(window, qapp)
    session_id = window.session.session_id
    window.close()  # closing before the last trial marks the session aborted
    return session_id


# ------------------------------------------------------------------ protocol
def test_protocol_version_is_label_plus_hash_and_deterministic() -> None:
    research = load_research_parameters()
    protocol = build_protocol(research)
    assert re.fullmatch(r"pilot-placeholder\+[0-9a-f]{12}", protocol.version)
    assert build_protocol(load_research_parameters()).version == protocol.version
    assert protocol.confirmed is False
    snapshot = protocol.stored_snapshot()
    assert snapshot["protocol_version"] == protocol.version
    for key in ("trial_count", "target_diameter_px", "foreperiod_ms", "stabilization_radius_px",
                "stabilization_movement_threshold_px", "stabilization_duration_ms", "random_seed"):
        assert key in snapshot["tasks"]["flick"]
    assert "timeout_ms" in snapshot["tasks"]["switching"]
    assert "trial_duration_ms" in snapshot["tasks"]["tracking"]
    assert snapshot["practice"]["trial_count"]["flick"] >= 0
    assert snapshot["task_order_method"] == "counterbalanced"
    assert snapshot["assignment_method"] == "participant_sequence_modulo_6"
    assert snapshot["available_task_orders"] == ["FTS", "FST", "TFS", "TSF", "SFT", "STF"]
    assert snapshot["practice"]["task_order_method"] == "match_assigned"


@pytest.mark.parametrize("section, key, value", [
    ("flick_task", "target_diameter_px", 41), ("switching_task", "timeout_ms", 2999),
    ("tracking_task", "stabilization_duration_ms", 301), ("tracking_task", "trial_count", 7),
    ("protocol", "practice_enabled", False),
])
def test_any_parameter_change_gives_a_new_protocol_version(section, key, value) -> None:
    research = load_research_parameters()
    before = build_protocol(research).version
    getattr(research, section)[key] = value
    assert build_protocol(research).version != before


def test_baseline_crosshair_change_gives_a_new_protocol_version() -> None:
    research = load_research_parameters()
    before = build_protocol(research).version
    research.baseline_crosshair["gap"] = 4
    assert build_protocol(research).version != before


@pytest.mark.parametrize("change", [
    {"available_task_orders": ["FTS", "FTS", "TFS", "TSF", "SFT", "STF"]},
    {"practice_trial_count": {"flick": -1, "tracking": 1, "switching": 1}},
    {"assignment_method": "uncontrolled_random"},
    {"label": ""},
])
def test_invalid_protocol_rejected(change) -> None:
    research = load_research_parameters()
    research.protocol.update(change)
    with pytest.raises(ValidationError):
        build_protocol(research)


def test_practice_disabled_means_zero_practice_trials() -> None:
    research = load_research_parameters()
    research.protocol["practice_enabled"] = False
    assert build_protocol(research).practice_count("flick") == 0


# --------------------------------------------------- practice -> experiment
def test_practice_then_transition_then_experimental_block(context, qapp) -> None:
    window = _flick(context, practice=2, trials=2)
    press_key(window, Qt.Key.Key_Space)
    assert window.phase == TrialPhase.PRACTICE
    assert window.plan is window.practice_plan and len(window.plan) == 2
    for _ in range(2):
        _flick_trial(window, qapp, hit=False)
    assert window.state == State.TRANSITION
    assert window.phase == TrialPhase.EXPERIMENTAL and window.trial_index == 0
    assert window.plan is window.experimental_plan
    assert window.results == [], "practice outcomes are not counted in the session summary"
    click(window, window._center_px())
    assert window.state == State.TRANSITION, "clicks do not start a trial on the transition screen"
    press_key(window, Qt.Key.Key_Space)
    assert window.state == State.WAIT_START
    for _ in range(2):
        _flick_trial(window, qapp)
    assert window.state == State.DONE
    assert window.results == [TrialResult.HIT, TrialResult.HIT]

    repo = context.repository
    session = repo.get_session(window.session.session_id)
    assert session.status == SessionStatus.COMPLETED
    trials = repo.list_trials(session.session_id)
    assert [t.trial_phase for t in trials] == [TrialPhase.PRACTICE] * 2 + [TrialPhase.EXPERIMENTAL] * 2
    assert [t.trial_number for t in trials] == [1, 2, 3, 4]
    assert len(session.task_config["practice_plan"]) == 2 and len(session.task_config["plan"]) == 2
    assert session.task_config["practice_plan"] != session.task_config["plan"][:2]
    assert repo.list_samples(trials[0].trial_id), "practice raw data is kept for audit"
    assert "Practice complete" in PRACTICE_COMPLETE_TEXT
    window.close()


def test_practice_trials_are_excluded_from_metrics(context, qapp) -> None:
    session_id = _run_flick(context, qapp, practice=2, trials=2)
    analysis = analyze_session(context.repository, session_id, store=False)
    assert analysis.metrics["practice_trials"] == 2
    assert analysis.metrics["trials"] == 2
    assert analysis.metrics["hit_rate"] == 1.0, "practice misses must not lower the hit rate"
    assert analysis.mismatches == []


def test_invalid_practice_trial_is_stored_as_practice_and_not_counted(context, qapp) -> None:
    window = _flick(context, practice=1, trials=1)
    press_key(window, Qt.Key.Key_Space)
    begin_foreperiod(window)
    center = window._center_px()
    move(window, QPointF(center.x() + 30, center.y()))
    assert window.invalid_trials == 0
    [row] = context.repository.list_trials(window.session.session_id)
    assert row.trial_phase == TrialPhase.PRACTICE and row.trial_status == TrialStatus.INVALID_PRE_MOVEMENT
    analysis = analyze_session(context.repository, window.session.session_id, store=False)
    assert analysis.metrics["invalid_pre_movement_count"] == 0
    window.close()


@pytest.mark.parametrize("kind", ["tracking", "switching"])
def test_practice_block_in_tracking_and_switching(context, qapp, kind) -> None:
    from app.ui.switching_window import SwitchingExperimentWindow
    from app.ui.tracking_window import TrackingExperimentWindow

    context.research.protocol["practice_enabled"] = True
    context.research.protocol["practice_trial_count"][kind] = 1
    getattr(context.research, f"{kind}_task").update(trial_count=1)
    window = (TrackingExperimentWindow if kind == "tracking" else SwitchingExperimentWindow)(context)
    window.resize(1400, 1000)
    window.show()
    press_key(window, Qt.Key.Key_Space)
    for block in range(2):
        start_trial(window, qapp)
        if kind == "tracking":
            window.timeout_timer.stop()
            window.sample_timer.stop()
            for i in range(1, 10):
                move(window, QPointF(*window.recorder.path.position(i * 10)))
            window._on_timeout_timer()
        else:
            for target in window._trial().targets:
                move(window, QPointF(target.x, target.y))
                click(window, QPointF(target.x, target.y))
        if block == 0:
            assert window.state == State.TRANSITION
            press_key(window, Qt.Key.Key_Space)
    assert window.state == State.DONE
    rows = context.repository.list_trials(window.session.session_id)
    phases = [r.trial_phase for r in rows]
    assert phases[0] == TrialPhase.PRACTICE and phases[-1] == TrialPhase.EXPERIMENTAL
    if kind == "switching":
        assert {r.extra["attempt"] for r in rows} == {1}, "attempt numbering restarts for the experimental block"
    analysis = analyze_session(context.repository, window.session.session_id, store=False)
    assert analysis.metrics["practice_trials"] == phases.count(TrialPhase.PRACTICE)
    assert analysis.metrics["trials"] == phases.count(TrialPhase.EXPERIMENTAL)
    window.close()


# ------------------------------------------------------- session snapshots
def test_session_stores_protocol_and_crosshair_snapshots(context, qapp) -> None:
    session_id = _run_flick(context, qapp, trials=1)
    session = context.repository.get_session(session_id)
    protocol = build_protocol(context.research)
    assert session.protocol_version == protocol.version
    assert session.protocol_snapshot == protocol.stored_snapshot()
    baseline = context.baseline_crosshair
    snapshot = session.crosshair_snapshot
    assert snapshot["crosshair_id"] == baseline.crosshair_id == session.crosshair_id
    for key in ("color", "size", "thickness", "gap", "outline_enabled", "outline_thickness", "opacity"):
        assert snapshot[key] == getattr(baseline, key)
    assert snapshot["px_per_unit"] == context.research.px_per_unit


def test_session_snapshots_are_immutable(context, qapp) -> None:
    session_id = _run_flick(context, qapp, trials=1)
    for column in ("protocol_version", "protocol_snapshot_json", "crosshair_snapshot_json"):
        with pytest.raises(sqlite3.IntegrityError):
            context.database.connection.execute(
                f"UPDATE sessions SET {column} = 'x' WHERE session_id = ?", (session_id,))


def test_historical_session_stays_interpretable_after_parameter_change(context, qapp) -> None:
    first = _run_flick(context, qapp, trials=2)
    repo = context.repository
    before = repo.get_session(first)
    metrics_before = analyze_session(repo, first, store=False).metrics
    old_size = context.research.flick_task["target_diameter_px"]

    context.research.flick_task.update(target_diameter_px=old_size + 10, timeout_ms=2500)
    context.research.baseline_crosshair["gap"] = 5
    second = _run_flick(context, qapp, trials=2)

    after = repo.get_session(first)
    assert after.protocol_snapshot == before.protocol_snapshot
    assert after.protocol_snapshot["tasks"]["flick"]["target_diameter_px"] == old_size
    assert after.crosshair_snapshot == before.crosshair_snapshot
    newer = repo.get_session(second)
    assert newer.protocol_version != after.protocol_version
    assert newer.protocol_snapshot["tasks"]["flick"]["target_diameter_px"] == old_size + 10
    assert analyze_session(repo, first, store=False).metrics == metrics_before


def test_legacy_session_without_protocol_loads(repo, session) -> None:
    loaded = repo.get_session(session.session_id)
    assert loaded.protocol_version is None
    assert loaded.protocol_snapshot is None and loaded.crosshair_snapshot is None


# ------------------------------------------------------ exclusion rules
def test_profile_uses_completed_baseline_only(context, qapp) -> None:
    repo = context.repository
    player = context.current_player.player_id
    baseline = _run_flick(context, qapp, practice=1, trials=2)
    candidate_run = RunSetup(context.baseline_crosshair, Condition.CANDIDATE, parent_session_id=baseline)
    candidate = _run_flick(context, qapp, run=candidate_run, trials=2)
    aborted = _run_flick(context, qapp, trials=2, abort=True)
    assert repo.get_session(candidate).condition == Condition.CANDIDATE
    assert repo.get_session(aborted).status == SessionStatus.ABORTED

    profile = build_profile(repo, player)
    flick = profile.tasks[ExperimentType.FLICK]
    assert flick.session_id == baseline, "newer candidate and aborted sessions must not be used"
    assert flick.metrics["hit_rate"] == 1.0, "practice misses must not enter the profile"
    assert flick.metrics["practice_trials"] == 1
    assert flick.protocol_version == repo.get_session(baseline).protocol_version


def test_comparison_excludes_practice_and_flags_protocol_change(context, qapp) -> None:
    baseline = _run_flick(context, qapp, practice=1, trials=2)
    context.research.flick_task.update(timeout_ms=2800)
    run = RunSetup(context.baseline_crosshair, Condition.CANDIDATE, parent_session_id=baseline)
    candidate = _run_flick(context, qapp, run=run, practice=1, trials=2)
    comparison = compare_sessions(context.repository, candidate)
    hit_rate = next(m for m in comparison.metrics if m.name == "hit_rate")
    assert hit_rate.baseline == hit_rate.candidate == 1.0
    assert any("protocol versions" in c for c in comparison.caveats)
