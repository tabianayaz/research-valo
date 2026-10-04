"""Tracking and Target Switching: plans, measures and simulated UI sessions."""

from __future__ import annotations

import math
from collections import Counter

import pytest
from PySide6.QtCore import QPointF, Qt

from app.config.research import load_research_parameters
from app.data.models import ExperimentType, SessionStatus, TrialEvent, TrialResult, TrialSample
from app.experiment.common import EventType
from app.experiment.switching import SwitchingConfig, generate_switching_plan
from app.experiment.tracking import (
    TrackingConfig,
    TrackingRecorder,
    compute_tracking_measures,
    generate_tracking_plan,
)
from app.ui.experiment_window import State
from app.utils.validators import ValidationError
from experiment_helpers import click, move, press_key, start_trial

PARAMS = load_research_parameters()
TRACKING = TrackingConfig.from_dict(PARAMS.tracking_task)
SWITCHING = SwitchingConfig.from_dict(PARAMS.switching_task)


# ------------------------------------------------------------------ tracking
def test_tracking_defaults_are_placeholders() -> None:
    assert TRACKING.confirmed is False and SWITCHING.confirmed is False


@pytest.mark.parametrize("change", [
    {"trial_duration_ms": 0}, {"path_component_weights": [0.5, 0.2]},
    {"path_frequencies_hz": [[0.1], [0.2]]}, {"sample_interval_ms": 0},
])
def test_tracking_invalid_config(change) -> None:
    with pytest.raises(ValidationError):
        TrackingConfig.from_dict({**PARAMS.tracking_task, **change})


def test_tracking_path_starts_at_centre_and_stays_inside() -> None:
    plan = generate_tracking_plan(TRACKING, 1920, 1080, seed=3)
    assert plan == generate_tracking_plan(TRACKING, 1920, 1080, seed=3)
    assert len(plan) == TRACKING.trial_count
    radius = TRACKING.target_diameter_px / 2
    for path in plan:
        assert path.position(0) == pytest.approx((960, 540))
        for t in range(0, TRACKING.trial_duration_ms + 1, 20):
            x, y = path.position(t)
            assert radius <= x <= 1920 - radius and radius <= y <= 1080 - radius
        assert path.mean_speed(TRACKING.trial_duration_ms) > 0


def test_tracking_amplitude_shrinks_for_small_arena_and_rejects_tiny() -> None:
    path = generate_tracking_plan(TRACKING, 800, 500, seed=1)[0]
    assert path.amplitude_x <= 400 - TRACKING.target_diameter_px / 2
    with pytest.raises(ValidationError):
        generate_tracking_plan(TRACKING, 120, 120, seed=1)


def test_tracking_measures_are_time_weighted() -> None:
    radius_ok = 10.0
    samples = [
        TrialSample(0, 100, 100, 100, 100, True),     # on target for 100 ms
        TrialSample(100, 100, 100, 130, 100, False),  # 30 px off for 300 ms
        TrialSample(400, 130, 100, 130, 100, True),   # end sample
    ]
    events = [
        TrialEvent(0, EventType.TARGET_ONSET, 100, 100),
        TrialEvent(400, EventType.TRIAL_END, 130, 100),
    ]
    m = compute_tracking_measures(samples, events, radius_ok * 2, 3)
    assert m.result == TrialResult.TRACKED
    assert m.on_target_ratio == pytest.approx(0.25)
    assert m.mean_distance == pytest.approx(30 * 300 / 400)
    assert m.rms_distance == pytest.approx(math.sqrt(900 * 300 / 400))
    assert m.reaction_time_ms == pytest.approx(400)
    assert m.movement_distance == pytest.approx(30)


def test_tracking_recorder_raw_is_reproducible() -> None:
    path = generate_tracking_plan(TRACKING, 1920, 1080, seed=3)[0]
    rec = TrackingRecorder(path, TRACKING)
    rec.start_click(5.0, 960, 540)
    rec.click(5.2, 960, 540)
    rec.target_shown(5.5, 960, 540)
    for i in range(1, 50):
        x, y = path.position(i * 20)
        rec.sample(5.5 + i * 0.02, round(x), round(y))
    rec.end(6.5, 960, 540)
    samples, events = rec.raw()
    assert rec.early_clicks == 1
    assert [e.event_type for e in events][-1] == EventType.TRIAL_END
    m = rec.measures()
    assert m.on_target_ratio > 0.9
    assert compute_tracking_measures(samples, events, TRACKING.target_diameter_px, 3) == m


# ----------------------------------------------------------------- switching
def test_switching_plan_balanced_separated_and_inside() -> None:
    plan = generate_switching_plan(SWITCHING, 1920, 1080, seed=5)
    assert plan == generate_switching_plan(SWITCHING, 1920, 1080, seed=5)
    switches = [t.planned_distance_px for trial in plan for t in trial.targets[1:]]
    assert Counter(switches) == {d: len(switches) // 2 for d in SWITCHING.switch_distances_px}
    radius = SWITCHING.target_diameter_px / 2
    for trial in plan:
        assert len(trial.targets) == SWITCHING.targets_per_trial
        points = [(960, 540)] + [(t.x, t.y) for t in trial.targets]
        for i, a in enumerate(points):
            for b in points[i + 1:]:
                assert math.dist(a, b) >= SWITCHING.min_separation_px - 0.01
        for prev, cur in zip(trial.targets, trial.targets[1:]):
            assert math.dist((prev.x, prev.y), (cur.x, cur.y)) == pytest.approx(cur.planned_distance_px, abs=0.01)
        for t in trial.targets:
            assert radius <= t.x <= 1920 - radius and radius <= t.y <= 1080 - radius


def test_switching_rejects_overlapping_config() -> None:
    with pytest.raises(ValidationError):
        SwitchingConfig.from_dict({**PARAMS.switching_task, "min_separation_px": 10})


# ------------------------------------------------------------- UI sessions
def test_simulated_tracking_session(context, qapp) -> None:
    from app.ui.tracking_window import TrackingExperimentWindow

    context.research.tracking_task.update(trial_count=2)
    window = TrackingExperimentWindow(context)
    window.resize(1400, 1000)
    window.show()
    press_key(window, Qt.Key.Key_Space)
    for _ in range(2):
        start_trial(window, qapp)
        window.timeout_timer.stop()
        window.sample_timer.stop()
        recorder = window.recorder
        for i in range(1, 20):
            x, y = recorder.path.position(i * 10)
            move(window, QPointF(x, y))
        window._on_timeout_timer()
    assert window.state == State.DONE
    session = context.repository.get_session(window.session.session_id)
    assert session.status == SessionStatus.COMPLETED
    assert session.experiment_type == ExperimentType.TRACKING
    trials = context.repository.list_trials(session.session_id)
    assert [t.result for t in trials] == [TrialResult.TRACKED] * 2
    assert all(t.extra["on_target_ratio"] is not None for t in trials)
    assert context.repository.list_samples(trials[0].trial_id)
    window.close()


def test_simulated_switching_session_stores_one_row_per_target(context, qapp) -> None:
    from app.ui.switching_window import SwitchingExperimentWindow

    context.research.switching_task.update(trial_count=2)
    window = SwitchingExperimentWindow(context)
    window.resize(1400, 1000)
    window.show()
    press_key(window, Qt.Key.Key_Space)
    for trial_index in range(2):
        start_trial(window, qapp)
        for seq in range(SWITCHING.targets_per_trial):
            target = window._active_target()
            point = QPointF(target.x, target.y) if (trial_index, seq) != (1, 1) else QPointF(5, 5)
            move(window, point)
            click(window, point)
    assert window.state == State.DONE
    rows = context.repository.list_trials(window.session.session_id)
    assert len(rows) == 2 * SWITCHING.targets_per_trial
    assert [r.extra["sequence_index"] for r in rows[:3]] == [0, 1, 2]
    assert rows[1].previous_target_id == rows[0].target_id
    assert rows[0].previous_target_id is None
    assert rows[4].result == TrialResult.MISS
    assert sum(r.result == TrialResult.HIT for r in rows) == len(rows) - 1
    switch_events = context.repository.list_events(rows[1].trial_id)
    assert switch_events[0].event_type == EventType.TARGET_ONSET and switch_events[0].t_ms == 0
    window.close()
