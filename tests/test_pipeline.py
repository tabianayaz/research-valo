"""Measure -> analyse -> recommend -> re-test -> compare, plus engine unit tests."""

from __future__ import annotations

import copy

import pytest
from PySide6.QtCore import QPointF, Qt

from app.analysis.comparison import MetricComparison, compare_sessions
from app.analysis.metrics import analyze_session
from app.analysis.profile import PlayerProfile, TaskProfile, build_profile
from app.config.research import load_research_parameters
from app.crosshair.config import CrosshairConfig
from app.data.models import Condition, CrosshairRecord, CrosshairRole, ExperimentType, SessionStatus
from app.recommendation.engine import (
    RecommendationConfig,
    blended_contrast,
    component_scores,
    effective_weights,
    evaluate_rules,
    score_candidates,
    store_recommendation,
)
from app.ui.experiment_window import RunSetup
from app.utils.validators import ValidationError
from experiment_helpers import click, move, press_key, start_trial

REC = load_research_parameters().recommendation


def candidate(name: str, **changes) -> CrosshairRecord:
    values = dict(color="#00FFFF", size=4, thickness=2, gap=2, outline_enabled=False,
                  outline_thickness=1, opacity=1.0, fidelity="exact")
    values.update(changes)
    return CrosshairRecord(name=name, role=CrosshairRole.CANDIDATE, **values)


def run_flick(context, qapp, run: RunSetup | None = None, trials: int = 4) -> int:
    from app.ui.flick_window import FlickExperimentWindow, State

    context.research.flick_task.update(trial_count=trials)
    window = FlickExperimentWindow(context, run)
    window.resize(1400, 1000)
    window.show()
    finished = []
    window.finished.connect(lambda sid, status: finished.append(sid))
    press_key(window, Qt.Key.Key_Space)
    for i in range(trials):
        start_trial(window, qapp)
        target = window._current_target()
        point = QPointF(target.x + (0 if i % 2 else 25), target.y)  # alternate hit / miss
        move(window, point)
        click(window, point)
    assert window.state == State.DONE
    window.close()
    return finished[0]


# ------------------------------------------------------------- engine units
def test_contrast_matches_wcag_extremes() -> None:
    assert blended_contrast("#FFFFFF", 1.0, "#000000") == pytest.approx(21, rel=1e-3)
    assert blended_contrast("#808080", 0.0, "#808080") == pytest.approx(1)


def test_component_scores_are_bounded() -> None:
    config = RecommendationConfig.from_dict(REC)
    big = CrosshairConfig.from_record(candidate("big", size=20, gap=20, thickness=10))
    small = CrosshairConfig.from_record(candidate("small", size=2, gap=0, thickness=1))
    for shape in (big, small):
        scores = component_scores(shape, "exact", config, "#3A3F45", 1.0)
        assert all(0.0 <= v <= 1.0 for v in scores.values())
    assert component_scores(small, "exact", config, "#3A3F45", 1.0)["center_precision"] > \
        component_scores(big, "exact", config, "#3A3F45", 1.0)["center_precision"]
    assert component_scores(small, "approximate", config, "#3A3F45", 1.0)["source_fidelity"] == 0.6


def test_rules_fire_only_with_data() -> None:
    config = RecommendationConfig.from_dict(REC)
    profile = PlayerProfile("P", {ExperimentType.FLICK: TaskProfile(
        ExperimentType.FLICK, 1, "", {"error_ratio_mean": 0.9, "timeout_rate": 0.0})})
    outcomes = {o.rule.rule_id: o for o in evaluate_rules(profile, config)}
    assert outcomes["flick_click_error"].status == "applied"
    assert outcomes["flick_timeouts"].status == "not applied"
    assert outcomes["tracking_time_on_target"].status == "no data"
    weights = effective_weights(list(outcomes.values()), config)
    assert weights["center_precision"] == config.base_weights["center_precision"] + 1


@pytest.mark.parametrize("mutate", [
    lambda d: d["base_weights"].pop("visibility"),
    lambda d: d["rules"][0].update(metric="flick.unknown"),
    lambda d: d["rules"][0].update(op=">="),
    lambda d: d.update(top_n=0),
])
def test_invalid_recommendation_config_rejected(mutate) -> None:
    data = copy.deepcopy(REC)
    mutate(data)
    with pytest.raises(ValidationError):
        RecommendationConfig.from_dict(data)


def test_metric_comparison_wording() -> None:
    m = MetricComparison("completion_time_median_ms", 500.0, 450.0)
    assert m.difference_text() == "-50 ms" and m.percent_text() == "-10.0 %"
    assert m.direction_text() == "lower with candidate" and m.desirable_direction == "lower"
    rate = MetricComparison("hit_rate", 0.5, 0.75)
    assert rate.difference_text() == "+25.0 pp" and rate.percent_text() == "–"
    assert MetricComparison("hit_rate", None, 0.5).direction_text() == "no data"


# --------------------------------------------------------------- pipeline
def test_full_pipeline(context, qapp) -> None:
    repo = context.repository
    for i, c in enumerate([candidate("A"), candidate("B", color="#FF00FF", gap=4),
                           candidate("A copy"), candidate("C", size=10, fidelity="approximate")]):
        repo.add_crosshair(c)
    base = context.baseline_crosshair
    repo.add_crosshair(CrosshairRecord(  # identical to the baseline -> excluded
        name="same as baseline", role=CrosshairRole.CANDIDATE, **base.parameter_dict(), fidelity="exact"))

    baseline_id = run_flick(context, qapp)
    analysis = analyze_session(repo, baseline_id)
    assert analysis.mismatches == []
    assert analysis.metrics["trials"] == 4 and analysis.metrics["hit_rate"] == pytest.approx(0.5)

    profile = build_profile(repo, "P-TASK")
    assert profile.source_session_ids == [baseline_id]
    assert ExperimentType.TRACKING in profile.missing_tasks

    result = score_candidates(repo, context.research, base, profile)
    assert result.pool_size == 3
    assert any("identical to the baseline" in e for e in result.excluded)
    assert any("same parameters" in e for e in result.excluded)
    assert [c.score for c in result.ranked] == sorted((c.score for c in result.ranked), reverse=True)
    rec_id = store_recommendation(repo, result)
    stored = repo.get_recommendation(rec_id)
    assert stored["source_session_ids"] == [baseline_id]
    assert len(stored["candidates"]) == min(3, result.pool_size)
    assert {r["status"] for r in stored["weights"]["rules"]} >= {"no data"}

    chosen = repo.get_crosshair(stored["candidates"][0]["crosshair_id"])
    repo.mark_candidate_selected(rec_id, chosen.crosshair_id)
    candidate_id = run_flick(context, qapp, RunSetup(chosen, Condition.CANDIDATE, baseline_id, rec_id))
    session = repo.get_session(candidate_id)
    assert (session.condition, session.parent_session_id, session.recommendation_id, session.crosshair_id) == \
        (Condition.CANDIDATE, baseline_id, rec_id, chosen.crosshair_id)
    assert session.task_config["plan"] == repo.get_session(baseline_id).task_config["plan"]

    # Candidate sessions never feed the profile.
    assert build_profile(repo, "P-TASK").source_session_ids == [baseline_id]

    comparison = compare_sessions(repo, candidate_id)
    assert comparison.baseline.session.session_id == baseline_id
    assert any("order effect" in c for c in comparison.caveats)
    hit = next(m for m in comparison.metrics if m.name == "hit_rate")
    assert hit.difference == pytest.approx(0.0)
    with pytest.raises(ValidationError):
        compare_sessions(repo, baseline_id)


def test_pages_render_pipeline(context, qapp) -> None:
    from app.ui.aim_selection_page import AimSelectionPage
    from app.ui.comparison_page import ComparisonPage
    from app.ui.history_page import HistoryPage
    from app.ui.recommendation_page import RecommendationPage
    from app.ui.results_page import ResultsPage

    repo = context.repository
    repo.add_crosshair(candidate("A"))
    repo.add_crosshair(candidate("B", color="#FF00FF", gap=4))

    custom = repo.add_crosshair(CrosshairRecord(
        name="My own", role=CrosshairRole.CUSTOM, color="#FFFF00", size=5, thickness=1, gap=1,
        outline_enabled=False, outline_thickness=1, opacity=1.0))
    assessment = AimSelectionPage(context)
    assessment.on_page_shown()
    runs_offered = [assessment.crosshair_combo.itemData(i) for i in range(assessment.crosshair_combo.count())]
    runs_offered = [r for r in runs_offered if r is not None]
    # Before any recommendation: baseline, own crosshair and database candidates, none linked to a run.
    assert runs_offered[0].condition == Condition.BASELINE
    assert {r.crosshair.name for r in runs_offered[1:]} == {"My own", "A", "B"}
    assert all(r.recommendation_id is None for r in runs_offered)
    own_index = next(i for i in range(assessment.crosshair_combo.count())
                     if assessment.crosshair_combo.itemData(i) is not None
                     and assessment.crosshair_combo.itemData(i).crosshair.crosshair_id == custom.crosshair_id)
    assessment.crosshair_combo.setCurrentIndex(own_index)
    assert not assessment.start_buttons[ExperimentType.FLICK].isEnabled()  # needs a baseline first

    recommendation = RecommendationPage(context)
    recommendation.on_page_shown()
    assert not recommendation.candidates_card.isVisibleTo(recommendation)
    recommendation.generate()  # no baseline yet -> refused
    assert repo.list_recommendations() == []

    baseline_id = run_flick(context, qapp)
    results = ResultsPage(context)
    results.on_page_shown()
    results.show_section(str(baseline_id))
    assert results.analysis.session.session_id == baseline_id
    assert results.table.rowCount() == 4

    recommendation.generate()
    runs = repo.list_recommendations()
    assert len(runs) == 1 and recommendation.candidates_box.count() == 2
    targets = []
    recommendation.navigate_requested.connect(targets.append)
    first = runs[0]["candidates"][0]["crosshair_id"]
    recommendation._try_candidate(first)
    assert targets == [f"assessment:candidate:{runs[0]['recommendation_id']}:{first}"]

    assessment.on_page_shown()
    assessment.show_section(targets[0].partition(":")[2])
    run = assessment.crosshair_combo.currentData()
    assert run.condition == Condition.CANDIDATE and run.crosshair.crosshair_id == first
    assert assessment.start_buttons[ExperimentType.FLICK].isEnabled()
    assert not assessment.start_buttons[ExperimentType.TRACKING].isEnabled()  # no tracking baseline
    assert assessment.parent_session_id(ExperimentType.FLICK) == baseline_id

    candidate_id = run_flick(context, qapp, RunSetup(run.crosshair, Condition.CANDIDATE, baseline_id,
                                                     run.recommendation_id))
    comparison = ComparisonPage(context)
    comparison.on_page_shown()
    comparison.show_section(str(candidate_id))
    assert comparison.comparison.candidate.session.session_id == candidate_id
    assert comparison.table.rowCount() == len(comparison.comparison.metrics)
    context.settings.exports_dir.mkdir(parents=True, exist_ok=True)
    comparison._export()
    assert list(context.settings.exports_dir.glob("comparison_*.csv"))

    history = HistoryPage(context)
    history.refresh()
    assert history.table.rowCount() == 2 and history.rec_table.rowCount() == 1
    opened = []
    history.navigate_requested.connect(opened.append)
    for row in range(2):
        history._open_session(row, 0)
    assert sorted(opened) == sorted([f"comparison:{candidate_id}", f"results:{baseline_id}"])
    assert repo.get_session(candidate_id).status == SessionStatus.COMPLETED
