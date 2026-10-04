"""Flick Aim: plan generation, raw recording, measures and a simulated UI session."""

from __future__ import annotations

import math
from collections import Counter

import pytest
from PySide6.QtCore import QPointF, Qt

from app.config.research import load_research_parameters
from app.data.models import SessionStatus, TrialEvent, TrialResult, TrialSample
from app.experiment.flick import (
    EventType,
    FlickConfig,
    FlickTarget,
    FlickTrialRecorder,
    compute_flick_measures,
    generate_plan,
)
from app.utils.validators import ValidationError
from experiment_helpers import click, move, press_key, start_trial

BASE = {
    "confirmed": False, "trial_count": 30, "target_diameter_px": 40,
    "target_distances_px": [150, 300, 450], "target_color": "#E8524A",
    "start_marker_diameter_px": 24, "start_marker_color": "#BFC5CC",
    "foreperiod_ms": [400, 900], "timeout_ms": 3000,
    "movement_onset_threshold_px": 3, "random_seed": 1,
    "stabilization_radius_px": 12, "stabilization_movement_threshold_px": 3, "stabilization_duration_ms": 300,
}
CONFIG = FlickConfig.from_dict(BASE)


# ------------------------------------------------------------------- config
def test_default_parameters_load() -> None:
    config = FlickConfig.from_dict(load_research_parameters().flick_task)
    assert config.confirmed is False
    assert config.trial_count >= 1


@pytest.mark.parametrize("change", [
    {"trial_count": 0}, {"timeout_ms": 0}, {"foreperiod_ms": [900, 400]},
    {"target_distances_px": []}, {"movement_onset_threshold_px": 0},
    {"stabilization_radius_px": 5}, {"stabilization_movement_threshold_px": 0},
    {"stabilization_duration_ms": -1},
])
def test_invalid_config_rejected(change) -> None:
    with pytest.raises(ValidationError):
        FlickConfig.from_dict({**BASE, **change})


# --------------------------------------------------------------------- plan
def test_plan_is_deterministic_balanced_and_inside_arena() -> None:
    plan = generate_plan(CONFIG, 1920, 1080, seed=7)
    assert plan == generate_plan(CONFIG, 1920, 1080, seed=7)
    assert plan != generate_plan(CONFIG, 1920, 1080, seed=8)
    assert Counter(t.planned_distance_px for t in plan) == {150: 10, 300: 10, 450: 10}
    radius = CONFIG.target_diameter_px / 2
    for t in plan:
        assert radius <= t.x <= 1920 - radius and radius <= t.y <= 1080 - radius
        assert math.hypot(t.x - 960, t.y - 540) == pytest.approx(t.planned_distance_px, abs=0.01)
        assert 400 <= t.foreperiod_ms <= 900


def test_plan_rejects_too_small_arena() -> None:
    with pytest.raises(ValidationError, match="too small"):
        generate_plan(CONFIG, 600, 400, seed=1)


# ------------------------------------------------------------------ measures
TARGET = FlickTarget(index=0, x=400.0, y=100.0, planned_distance_px=300,
                     angle_deg=90.0, foreperiod_ms=500)


def run_trial(click_at: tuple[float, float] | None) -> FlickTrialRecorder:
    rec = FlickTrialRecorder(TARGET, CONFIG)
    rec.start_click(10.0, 400, 400)
    rec.move(10.1, 401, 400)
    rec.click(10.2, 401, 400)            # early click during the foreperiod
    rec.target_shown(10.5, 401, 400)
    rec.move(10.6, 402, 400)             # 1 px: below the onset threshold
    rec.move(10.7, 401, 300)             # onset
    rec.move(10.8, 401, 102)
    if click_at is None:
        rec.timeout(13.5, 401, 102)
    else:
        assert rec.click(10.9, *click_at)
    rec.move(11.0, 0, 0)                 # after the end: ignored
    return rec


def test_hit_measures() -> None:
    rec = run_trial((401, 102))
    m = rec.measures()
    assert m.result == TrialResult.HIT
    assert m.reaction_time_ms == pytest.approx(200)
    assert m.completion_time_ms == pytest.approx(400)
    assert m.movement_time_ms == pytest.approx(200)
    assert m.error_distance == pytest.approx(math.hypot(1, 2))
    assert m.target_distance == pytest.approx(math.hypot(1, 300))
    assert m.movement_distance == pytest.approx(1 + math.hypot(1, 100) + 198 + 0)
    assert rec.early_clicks == 1


def test_miss_and_timeout() -> None:
    assert run_trial((401, 300)).measures().result == TrialResult.MISS
    timeout = run_trial(None).measures()
    assert timeout.result == TrialResult.TIMEOUT
    assert timeout.completion_time_ms is None and timeout.error_distance is None
    assert timeout.reaction_time_ms == pytest.approx(200)


def test_raw_data_is_relative_and_reproducible() -> None:
    rec = run_trial((401, 102))
    samples, events = rec.raw()
    assert [e.event_type for e in events] == [
        EventType.START_CLICK, EventType.EARLY_CLICK, EventType.TARGET_ONSET, EventType.CLICK]
    assert events[0].t_ms == pytest.approx(-500)
    assert events[-1].is_hit is True
    assert samples[0].target_x is None and samples[-1].target_x == TARGET.x
    assert all(s.t_ms <= 400 for s in samples)
    recomputed = compute_flick_measures(samples, events, TARGET.x, TARGET.y, 40, 3)
    assert recomputed == rec.measures()


def test_missing_onset_is_incomplete() -> None:
    events = [TrialEvent(t_ms=5, event_type=EventType.CLICK, x=0, y=0)]
    assert compute_flick_measures([TrialSample(0, 0, 0)], events, 0, 0, 40, 3).result == TrialResult.INCOMPLETE


# --------------------------------------------------------------- UI session
def make_window(context, trial_count: int | None = None):
    from app.ui.flick_window import FlickExperimentWindow

    if trial_count is not None:
        context.research.flick_task.update(trial_count=trial_count)
    window = FlickExperimentWindow(context)
    window.resize(1400, 1000)
    window.show()
    return window


def test_simulated_flick_session_stores_raw_trials(context, qapp) -> None:
    from app.ui.flick_window import State

    window = make_window(context, trial_count=3)
    finished = []
    window.finished.connect(lambda sid, status: finished.append((sid, status)))
    press_key(window, Qt.Key.Key_Space)
    assert window.state == State.WAIT_START

    center = window._center_px()
    for i in range(3):
        start_trial(window, qapp)
        target = window._current_target()
        point = QPointF(target.x, target.y) if i < 2 else center
        move(window, point)
        click(window, point)

    assert window.state == State.DONE
    session_id = finished[0][0]
    assert finished == [(session_id, "completed")]
    repo = context.repository
    session = repo.get_session(session_id)
    assert session.status == SessionStatus.COMPLETED
    assert session.task_config["timing_definition"]["version"] == "flick-timing-2"
    trials = repo.list_trials(session_id)
    assert [t.result for t in trials] == [TrialResult.HIT, TrialResult.HIT, TrialResult.MISS]
    events = repo.list_events(trials[0].trial_id)
    assert [e.event_type for e in events][-2:] == [EventType.TARGET_ONSET, EventType.CLICK]
    assert repo.list_samples(trials[0].trial_id)
    window.close()


def test_escape_at_intro_creates_no_session(context) -> None:
    window = make_window(context)
    finished = []
    window.finished.connect(lambda sid, status: finished.append((sid, status)))
    press_key(window, Qt.Key.Key_Escape)
    assert finished == [(0, "aborted")]
    assert context.repository.list_session_summaries() == []


def test_closing_mid_session_marks_aborted_and_keeps_trials(context, qapp) -> None:
    window = make_window(context)
    press_key(window, Qt.Key.Key_Space)
    start_trial(window, qapp)
    target = window._current_target()
    click(window, QPointF(target.x, target.y))
    session_id = window.session.session_id
    window.close()
    assert context.repository.get_session(session_id).status == SessionStatus.ABORTED
    assert len(context.repository.list_trials(session_id)) == 1
