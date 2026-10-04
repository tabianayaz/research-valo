"""Descriptive comparison of a candidate session with its baseline (Milestone 12).

Only measured differences are reported: candidate minus baseline, and a
percentage difference for metrics on a ratio scale (ms, px). Ratios (hit
rate, time on target, ...) are compared in percentage points instead, because
a relative change of a proportion is easy to misread. No inferential
statistics are computed: two single sessions cannot separate a crosshair
effect from session-to-session variation or practice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.metrics import METRICS, TASK_METRICS, SessionAnalysis, analyze_session, format_metric
from app.data.models import Condition, ExperimentType, SessionStatus
from app.data.repository import Repository
from app.utils.validators import ValidationError

PERCENT_UNITS = ("ms", "px")
HIGH_MOVING_AT_ONSET = 0.25
DESIRABLE = {"better": "higher", "worse": "lower", "neutral": "–"}


@dataclass
class MetricComparison:
    name: str
    baseline: float | None
    candidate: float | None

    @property
    def definition(self):
        return METRICS[self.name]

    @property
    def difference(self) -> float | None:
        if self.baseline is None or self.candidate is None:
            return None
        return self.candidate - self.baseline

    @property
    def percent_difference(self) -> float | None:
        if self.difference is None or self.definition.unit not in PERCENT_UNITS or not self.baseline:
            return None
        return self.difference / self.baseline * 100

    @property
    def desirable_direction(self) -> str:
        return DESIRABLE[self.definition.higher_is]

    def difference_text(self) -> str:
        diff = self.difference
        if diff is None:
            return "–"
        unit = self.definition.unit
        if unit == "ratio" and self.name != "error_ratio_mean":
            return f"{diff * 100:+.1f} pp"
        if unit == "count":
            return f"{diff:+.0f}"
        digits = 0 if unit == "ms" else 2 if unit == "ratio" else 1
        return f"{diff:+.{digits}f} {unit}".strip()

    def percent_text(self) -> str:
        pct = self.percent_difference
        return "–" if pct is None else f"{pct:+.1f} %"

    def direction_text(self) -> str:
        diff = self.difference
        if diff is None:
            return "no data"
        if abs(diff) < 1e-9:
            return "no measured difference"
        return "higher with candidate" if diff > 0 else "lower with candidate"


@dataclass
class SessionComparison:
    baseline: SessionAnalysis
    candidate: SessionAnalysis
    metrics: list[MetricComparison]
    caveats: list[str] = field(default_factory=list)

    @property
    def task(self) -> ExperimentType:
        return ExperimentType(self.candidate.session.experiment_type)

    def table_rows(self) -> list[list[str]]:
        return [
            [m.definition.label, format_metric(m.name, m.baseline), format_metric(m.name, m.candidate),
             m.difference_text(), m.percent_text(), m.direction_text(), m.desirable_direction]
            for m in self.metrics
        ]

    def csv_rows(self) -> list[list]:
        b, c = self.baseline.session, self.candidate.session
        return [
            [c.player_id, str(c.experiment_type), b.session_id, c.session_id, b.crosshair_id, c.crosshair_id,
             c.recommendation_id, m.name, m.definition.unit, m.baseline, m.candidate, m.difference,
             m.percent_difference, m.direction_text(), m.desirable_direction]
            for m in self.metrics
        ]


CSV_HEADER = ["player_id", "task", "baseline_session_id", "candidate_session_id", "baseline_crosshair_id",
              "candidate_crosshair_id", "recommendation_id", "metric", "unit", "baseline", "candidate",
              "difference", "percent_difference", "direction", "desirable_direction"]


def _task_config(analysis: SessionAnalysis) -> dict:
    config = analysis.session.task_config or {}
    return {"task": config.get(str(analysis.session.experiment_type)), "arena_px": config.get("arena_px")}


def _timing_versions(analysis: SessionAnalysis) -> set:
    return {(row.trial.extra or {}).get("timing_definition") for row in analysis.rows if not row.excluded}


def compare_sessions(repo: Repository, candidate_session_id: int) -> SessionComparison:
    candidate_session = repo.get_session(candidate_session_id)
    if candidate_session is None:
        raise ValidationError(f"Session {candidate_session_id} does not exist")
    if candidate_session.condition != Condition.CANDIDATE:
        raise ValidationError(f"Session {candidate_session_id} is not a candidate session")
    if candidate_session.parent_session_id is None:
        raise ValidationError(f"Candidate session {candidate_session_id} has no linked baseline session")
    candidate = analyze_session(repo, candidate_session_id)
    baseline = analyze_session(repo, candidate_session.parent_session_id)
    task = ExperimentType(candidate_session.experiment_type)
    metrics = [MetricComparison(name, baseline.metrics.get(name), candidate.metrics.get(name))
               for name in TASK_METRICS[task]]

    caveats = [
        "Descriptive comparison of two single sessions. No statistical test was performed; differences "
        "may be within normal session-to-session variation.",
        "The candidate session was recorded after the baseline session with the same target sequence, so "
        "practice or familiarity can contribute to any difference (order effect).",
    ]
    for analysis, role in ((baseline, "baseline"), (candidate, "candidate")):
        if analysis.session.status != SessionStatus.COMPLETED:
            caveats.append(f"The {role} session is {analysis.session.status}; only its saved trials are used.")
        moving = analysis.metrics.get("moving_at_onset_rate")
        if moving is not None and moving > HIGH_MOVING_AT_ONSET:
            caveats.append(f"In the {role} session the crosshair was moving at target onset in "
                           f"{moving * 100:.0f} % of trials, so reaction time is hard to interpret.")
        if analysis.mismatches:
            caveats.append(f"The {role} session has {len(analysis.mismatches)} recomputation mismatches.")
        fallback = int(analysis.metrics.get("timing_fallback_count") or 0)
        if fallback:
            caveats.append(f"The {role} session has {fallback} timing-fallback trials; they are excluded from "
                           "time measures, so time metrics use fewer trials.")
        invalid = int(analysis.metrics.get("invalid_pre_movement_count") or 0)
        if invalid:
            caveats.append(f"The {role} session has {invalid} trials invalidated for movement before the target "
                           "appeared (repeated, excluded from all metrics).")
    if baseline.session.protocol_version != candidate.session.protocol_version:
        caveats.append(f"The sessions were run under different protocol versions "
                       f"({baseline.session.protocol_version or 'not recorded'} vs "
                       f"{candidate.session.protocol_version or 'not recorded'}); task parameters may differ.")
    if _timing_versions(baseline) != _timing_versions(candidate):
        caveats.append("The two sessions were recorded with different timing procedures (e.g. one without the "
                       "pre-trial stabilization period), so their time measures are not directly comparable.")
    if _task_config(baseline) != _task_config(candidate):
        caveats.append("Task parameters or the arena size differ between the two sessions, so the target "
                       "sequences are not identical.")
    if not (candidate.session.task_config or {}).get(str(task), {}).get("confirmed", False):
        caveats.append("Task parameters are placeholders (confirmed = false).")
    return SessionComparison(baseline, candidate, metrics, caveats)
