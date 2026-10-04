"""Session metrics recomputed from raw trial data.

Every trial measure is recomputed from the stored samples and events (not
read from the trial columns), so the metrics are reproducible from raw data.
The recomputed values are compared with the values stored at recording time
and any mismatch is reported.

Trial validity (analysis version ``metrics-2``). A trial can be valid for
one measure and invalid for another; nothing is discarded silently and the
counts of excluded trials are reported as metrics.
    * ``invalid_pre_movement`` and practice trials (``trial_phase =
      practice``): excluded from every metric, and therefore from the player
      profile, the recommendation and comparisons (counted in
      ``invalid_pre_movement_count`` / ``practice_trials``).
    * valid_for_reaction_time: status ``valid``, movement onset detected, and
      the crosshair was not moving in the 100 ms before t0
      (``moving_at_onset``). Switching segments after the first start at the
      previous click and have no pre-onset window; they are valid if their
      status is valid.
    * valid_for_completion_time: status ``valid`` and a hit (completion and
      switching times use hits only).
    * valid_for_accuracy (hit rate, timeout rate, click error): status
      ``valid`` or ``timing_fallback`` (outcome and click position do not
      depend on t0).
    * valid_for_tracking (time on target, distances): status ``valid``; the
      target path is defined relative to t0, so fallback trials are excluded.
    * Trials recorded before trial status existed (NULL): ``timing_fallback``
      if ``extra.onset_from_paint`` is false (first segments only), else
      ``valid``.

Aggregation rules
    * Medians are used for time measures (robust to single slow trials);
      means are reported alongside for completion time.
    * Error distance uses clicked trials (hits and misses); timeouts have
      no click. ``error_ratio`` is error distance divided by the target
      radius (1.0 = edge of the target).
    * Target Switching: if a trial was restarted (cancelled abort), only the
      latest attempt of each switching trial is used. Times of the first
      target in a sequence are reported separately from switches.
    * No metric combines tasks; there is no overall aim score.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

from app.data.models import ExperimentType, Session, Trial, TrialPhase, TrialResult, TrialStatus
from app.data.repository import Repository
from app.experiment.pointing import compute_pointing_measures
from app.experiment.tracking import compute_tracking_measures

ANALYSIS_VERSION = "metrics-2"
MISMATCH_TOLERANCE = 1e-6
MOVING_WINDOW_MS = 100.0


@dataclass(frozen=True)
class MetricDef:
    label: str
    unit: str
    higher_is: str  # "better", "worse" or "neutral" - descriptive only, used for wording
    description: str


METRICS: dict[str, MetricDef] = {
    "trials": MetricDef("Trials", "count", "neutral", "Trials (or targets) analysed"),
    "hit_rate": MetricDef("Hit rate", "ratio", "better", "Hits / trials"),
    "timeout_rate": MetricDef("Timeout rate", "ratio", "worse", "Timeouts / trials"),
    "reaction_time_median_ms": MetricDef(
        "Reaction time (median)", "ms", "worse", "t0 -> movement onset"),
    "completion_time_median_ms": MetricDef(
        "Completion time (median, hits)", "ms", "worse", "t0 -> click, hit trials"),
    "completion_time_mean_ms": MetricDef(
        "Completion time (mean, hits)", "ms", "worse", "t0 -> click, hit trials"),
    "error_distance_mean_px": MetricDef(
        "Click error (mean)", "px", "worse", "Crosshair-to-target-centre distance at the click"),
    "error_ratio_mean": MetricDef(
        "Click error / target radius (mean)", "ratio", "worse", "1.0 = edge of the target"),
    "on_target_ratio_mean": MetricDef(
        "Time on target (mean)", "ratio", "better", "Share of trial time within the target radius"),
    "mean_distance_mean_px": MetricDef(
        "Distance to target (mean)", "px", "worse", "Time-weighted crosshair-to-target distance"),
    "rms_distance_mean_px": MetricDef(
        "Distance to target (RMS, mean)", "px", "worse", "Time-weighted root-mean-square distance"),
    "switching_time_median_ms": MetricDef(
        "Switching time (median, hits)", "ms", "worse", "Previous click -> click on the next target"),
    "first_target_time_median_ms": MetricDef(
        "First-target time (median, hits)", "ms", "worse", "t0 -> click on the first target"),
    "moving_at_onset_rate": MetricDef(
        "Moving at target onset", "ratio", "neutral",
        "Trials where the crosshair moved in the 100 ms before t0; their reaction time is excluded"),
    "reaction_time_valid_trials": MetricDef(
        "Trials valid for reaction time", "count", "neutral",
        "Valid status, movement onset detected, not moving at target onset"),
    "invalid_pre_movement_count": MetricDef(
        "Invalid trials (moved before target)", "count", "neutral",
        "Trials invalidated because the cursor moved during the foreperiod; repeated, excluded from all metrics"),
    "timing_fallback_count": MetricDef(
        "Timing-fallback trials", "count", "neutral",
        "Target onset taken from the fallback timer; excluded from time measures, kept for accuracy"),
    "practice_trials": MetricDef(
        "Practice trials (not analysed)", "count", "neutral",
        "Practice rows stored for audit; excluded from every metric, the profile and comparisons"),
}

VALIDITY_METRICS = ("reaction_time_valid_trials", "invalid_pre_movement_count", "timing_fallback_count",
                    "practice_trials")

TASK_METRICS: dict[ExperimentType, tuple[str, ...]] = {
    ExperimentType.FLICK: (
        "trials", "hit_rate", "timeout_rate", "reaction_time_median_ms",
        "completion_time_median_ms", "completion_time_mean_ms",
        "error_distance_mean_px", "error_ratio_mean", "moving_at_onset_rate", *VALIDITY_METRICS,
    ),
    ExperimentType.TRACKING: (
        "trials", "on_target_ratio_mean", "mean_distance_mean_px", "rms_distance_mean_px",
        "reaction_time_median_ms", "moving_at_onset_rate", *VALIDITY_METRICS,
    ),
    ExperimentType.SWITCHING: (
        "trials", "hit_rate", "timeout_rate", "reaction_time_median_ms",
        "switching_time_median_ms", "first_target_time_median_ms",
        "error_distance_mean_px", "error_ratio_mean", "moving_at_onset_rate", *VALIDITY_METRICS,
    ),
}


@dataclass
class TrialRow:
    """One trial with its measures recomputed from raw samples/events."""

    trial: Trial
    result: TrialResult
    reaction_time_ms: float | None = None
    completion_time_ms: float | None = None
    error_distance: float | None = None
    target_distance: float | None = None
    movement_distance: float | None = None
    on_target_ratio: float | None = None
    mean_distance: float | None = None
    rms_distance: float | None = None
    is_switch: bool = False
    moving_at_onset: bool | None = None

    @property
    def error_ratio(self) -> float | None:
        if self.error_distance is None or not self.trial.target_size:
            return None
        return self.error_distance / (self.trial.target_size / 2)

    @property
    def status(self) -> TrialStatus:
        return effective_status(self.trial)

    @property
    def excluded(self) -> bool:
        return self.status == TrialStatus.INVALID_PRE_MOVEMENT or self.trial.trial_phase == TrialPhase.PRACTICE

    @property
    def valid_for_reaction_time(self) -> bool:
        return (not self.excluded and self.status == TrialStatus.VALID and self.reaction_time_ms is not None
                and self.moving_at_onset is not True)

    @property
    def valid_for_completion_time(self) -> bool:
        return not self.excluded and self.status == TrialStatus.VALID and self.result == TrialResult.HIT

    @property
    def valid_for_accuracy(self) -> bool:
        return (not self.excluded and self.result != TrialResult.INCOMPLETE
                and self.status in (TrialStatus.VALID, TrialStatus.TIMING_FALLBACK))

    @property
    def valid_for_tracking(self) -> bool:
        return not self.excluded and self.status == TrialStatus.VALID and self.result == TrialResult.TRACKED

    def validity_label(self) -> str:
        if self.trial.trial_phase == TrialPhase.PRACTICE:
            return "practice"
        if self.status == TrialStatus.INVALID_PRE_MOVEMENT:
            return "invalid: moved before target"
        if self.status == TrialStatus.TIMING_FALLBACK:
            return "timing fallback"
        if self.moving_at_onset:
            return "valid (RT excluded: moving at onset)"
        return "valid"


def effective_status(trial: Trial) -> TrialStatus:
    """Stored status, or the status derived for trials recorded before trial status existed."""
    if trial.trial_status is not None:
        return TrialStatus(trial.trial_status)
    extra = trial.extra or {}
    if extra.get("onset_from_paint") is False and not extra.get("is_switch"):
        return TrialStatus.TIMING_FALLBACK
    return TrialStatus.VALID


@dataclass
class SessionAnalysis:
    session: Session
    rows: list[TrialRow]
    metrics: dict[str, float | None]
    mismatches: list[str] = field(default_factory=list)
    excluded_rows: int = 0

    def metric_items(self) -> list[tuple[str, MetricDef, float | None]]:
        task = ExperimentType(self.session.experiment_type)
        return [(name, METRICS[name], self.metrics.get(name)) for name in TASK_METRICS[task]]


def _threshold(session: Session) -> float:
    config = (session.task_config or {}).get(str(session.experiment_type), {})
    return float(config.get("movement_onset_threshold_px", 3))


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=MISMATCH_TOLERANCE)


def recompute_rows(repo: Repository, session: Session) -> tuple[list[TrialRow], list[str]]:
    threshold = _threshold(session)
    task = ExperimentType(session.experiment_type)
    rows, mismatches = [], []
    for trial in repo.list_trials(session.session_id):
        samples = repo.list_samples(trial.trial_id)
        events = repo.list_events(trial.trial_id)
        if task == ExperimentType.TRACKING:
            m = compute_tracking_measures(samples, events, trial.target_size, threshold)
            row = TrialRow(
                trial=trial, result=m.result, reaction_time_ms=m.reaction_time_ms,
                completion_time_ms=m.duration_ms, movement_distance=m.movement_distance,
                on_target_ratio=m.on_target_ratio, mean_distance=m.mean_distance,
                rms_distance=m.rms_distance,
            )
            pairs = [("error_distance", trial.error_distance, m.mean_distance)]
        else:
            m = compute_pointing_measures(samples, events, trial.target_x, trial.target_y,
                                          trial.target_size, threshold)
            row = TrialRow(
                trial=trial, result=m.result, reaction_time_ms=m.reaction_time_ms,
                completion_time_ms=m.completion_time_ms, error_distance=m.error_distance,
                target_distance=m.target_distance, movement_distance=m.movement_distance,
                is_switch=bool((trial.extra or {}).get("is_switch")),
            )
            pairs = [("error_distance", trial.error_distance, m.error_distance),
                     ("completion_time_ms", trial.completion_time_ms, m.completion_time_ms)]
        row.moving_at_onset = _moving_at_onset(samples, events, threshold)
        pairs.append(("reaction_time_ms", trial.reaction_time_ms, m.reaction_time_ms))
        if TrialResult(trial.result) != m.result:
            mismatches.append(f"trial {trial.trial_number}: result {trial.result} vs recomputed {m.result}")
        for name, stored, recomputed in pairs:
            if not _close(stored, recomputed):
                mismatches.append(f"trial {trial.trial_number}: {name} {stored} vs recomputed {recomputed}")
        rows.append(row)
    return rows, mismatches


def _moving_at_onset(samples, events, threshold: float) -> bool | None:
    """True if the crosshair moved >= threshold during the MOVING_WINDOW_MS before t = 0.

    Reaction time is measured from the crosshair position at t = 0, so it is
    only interpretable when the crosshair was (nearly) still at onset.
    Segments that start at a click (switching sequence_index >= 1) have no
    pre-onset samples and return None.
    """
    onset = next((e for e in events if e.event_type == "target_onset"), None)
    before = [s for s in samples if -MOVING_WINDOW_MS <= s.t_ms < 0]
    if onset is None or not before:
        return None
    return any(math.hypot(s.cursor_x - onset.x, s.cursor_y - onset.y) >= threshold for s in before)


def _latest_attempts(rows: list[TrialRow]) -> list[TrialRow]:
    """Latest attempt of each experimental switching trial; invalid and practice rows are kept for counting."""
    def keep_all(row: TrialRow) -> bool:
        return row.excluded

    latest: dict[Any, int] = {}
    for row in rows:
        if keep_all(row):
            continue
        extra = row.trial.extra or {}
        key = extra.get("switching_trial")
        latest[key] = max(latest.get(key, 0), int(extra.get("attempt", 1)))
    return [r for r in rows
            if keep_all(r)
            or int((r.trial.extra or {}).get("attempt", 1)) == latest[(r.trial.extra or {}).get("switching_trial")]]


def _median(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.fmean(clean) if clean else None


def _ratio(count: int, total: int) -> float | None:
    return count / total if total else None


def compute_metrics(task: ExperimentType, rows: list[TrialRow]) -> dict[str, float | None]:
    """Task-level metrics using the per-measure validity rules in the module docstring."""
    analysed = [r for r in rows if not r.excluded and r.result != TrialResult.INCOMPLETE]
    rt_rows = [r for r in analysed if r.valid_for_reaction_time]
    with_onset_info = [r for r in analysed if r.moving_at_onset is not None]
    metrics: dict[str, float | None] = {
        "trials": float(len(analysed)),
        "reaction_time_median_ms": _median([r.reaction_time_ms for r in rt_rows]),
        "moving_at_onset_rate": _ratio(sum(r.moving_at_onset for r in with_onset_info), len(with_onset_info)),
        "reaction_time_valid_trials": float(len(rt_rows)),
        "invalid_pre_movement_count": float(sum(r.status == TrialStatus.INVALID_PRE_MOVEMENT
                                                and r.trial.trial_phase != TrialPhase.PRACTICE for r in rows)),
        "practice_trials": float(sum(r.trial.trial_phase == TrialPhase.PRACTICE for r in rows)),
        "timing_fallback_count": float(sum(r.status == TrialStatus.TIMING_FALLBACK and not r.excluded
                                           for r in rows)),
    }
    if task == ExperimentType.TRACKING:
        tracked = [r for r in analysed if r.valid_for_tracking]
        metrics.update(
            on_target_ratio_mean=_mean([r.on_target_ratio for r in tracked]),
            mean_distance_mean_px=_mean([r.mean_distance for r in tracked]),
            rms_distance_mean_px=_mean([r.rms_distance for r in tracked]),
        )
        return metrics
    accuracy = [r for r in analysed if r.valid_for_accuracy]
    n = len(accuracy)
    clicked = [r for r in accuracy if r.result in (TrialResult.HIT, TrialResult.MISS)]
    timed_hits = [r for r in analysed if r.valid_for_completion_time]
    metrics.update(
        hit_rate=_ratio(sum(r.result == TrialResult.HIT for r in accuracy), n),
        timeout_rate=_ratio(sum(r.result == TrialResult.TIMEOUT for r in accuracy), n),
        error_distance_mean_px=_mean([r.error_distance for r in clicked]),
        error_ratio_mean=_mean([r.error_ratio for r in clicked]),
    )
    if task == ExperimentType.FLICK:
        metrics.update(
            completion_time_median_ms=_median([r.completion_time_ms for r in timed_hits]),
            completion_time_mean_ms=_mean([r.completion_time_ms for r in timed_hits]),
        )
    else:
        metrics.update(
            switching_time_median_ms=_median([r.completion_time_ms for r in timed_hits if r.is_switch]),
            first_target_time_median_ms=_median([r.completion_time_ms for r in timed_hits if not r.is_switch]),
        )
    return metrics


def analyze_session(repo: Repository, session_id: int, store: bool = True) -> SessionAnalysis:
    session = repo.get_session(session_id)
    if session is None:
        raise ValueError(f"Unknown session {session_id}")
    task = ExperimentType(session.experiment_type)
    rows, mismatches = recompute_rows(repo, session)
    used = _latest_attempts(rows) if task == ExperimentType.SWITCHING else rows
    metrics = compute_metrics(task, used)
    if store:
        repo.save_metrics(
            session_id,
            {name: (value, METRICS[name].unit) for name, value in metrics.items()},
            ANALYSIS_VERSION,
        )
    return SessionAnalysis(session, rows, metrics, mismatches, excluded_rows=len(rows) - len(used))


def format_metric(name: str, value: float | None) -> str:
    if value is None:
        return "–"
    unit = METRICS[name].unit
    if unit == "ratio" and (name.endswith("_rate") or name == "on_target_ratio_mean"):
        return f"{value * 100:.1f} %"
    if unit == "ms":
        return f"{value:.0f} ms"
    if unit == "px":
        return f"{value:.1f} px"
    if unit == "count":
        return f"{value:.0f}"
    return f"{value:.2f}"
