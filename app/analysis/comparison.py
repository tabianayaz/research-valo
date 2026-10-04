"""Descriptive comparison of a candidate session with its baseline (Milestone 12),
and of the three conditions of a crosshair evaluation cycle (Phase 5:
Baseline→Standard, Baseline→Candidate, Standard→Candidate).

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
from app.data.models import Condition, ConditionEvaluation, ExperimentType, SessionStatus
from app.data.repository import Repository
from app.utils.validators import ValidationError

PERCENT_UNITS = ("ms", "px")
HIGH_MOVING_AT_ONSET = 0.25
DESIRABLE = {"better": "higher", "worse": "lower", "neutral": "–"}


@dataclass
class MetricComparison:
    """``baseline`` is the reference value and ``candidate`` the compared value.

    In three-condition comparisons the pair can also be Baseline→Standard or
    Standard→Candidate; ``other_label`` names the compared condition.
    """

    name: str
    baseline: float | None
    candidate: float | None
    other_label: str = "candidate"

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
        return f"{'higher' if diff > 0 else 'lower'} with {self.other_label}"

    def amount_text(self) -> str:
        """Unsigned size of the difference: percent for ms/px metrics, otherwise the unit difference."""
        pct = self.percent_difference
        if pct is not None:
            return f"{abs(pct):.1f}%"
        return self.difference_text().lstrip("+-")

    def summary(self, reference: str, other: str) -> tuple[str, dict[str, str]]:
        """Descriptive sentence template and values, e.g. "Candidate condition was 4.2% lower than ..."."""
        diff = self.difference
        if diff is None:
            return "No data for {other} or {reference} condition.", {"other": other, "reference": reference}
        if abs(diff) < 1e-9:
            return ("{other} condition showed no measured difference from {reference} condition.",
                    {"other": other, "reference": reference})
        template = ("{other} condition was {amount} higher than {reference} condition." if diff > 0
                    else "{other} condition was {amount} lower than {reference} condition.")
        return template, {"other": other, "reference": reference, "amount": self.amount_text()}

    def summary_text(self, reference: str, other: str) -> str:
        template, values = self.summary(reference, other)
        return template.format(**values)


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
    """Task parameters without the seed: conditions deliberately use different seeds (Phase 5)."""
    config = analysis.session.task_config or {}
    task = config.get(str(analysis.session.experiment_type))
    if isinstance(task, dict):
        task = {key: value for key, value in task.items() if key != "random_seed"}
    return {"task": task, "arena_px": config.get("arena_px")}


def _timing_versions(analysis: SessionAnalysis) -> set:
    return {(row.trial.extra or {}).get("timing_definition") for row in analysis.rows if not row.excluded}


def _session_caveats(analysis: SessionAnalysis, role: str) -> list[str]:
    caveats = []
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
    return caveats


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

    same_seed = baseline.session.random_seed == candidate_session.random_seed
    caveats = [
        "Descriptive comparison of two single sessions. No statistical test was performed; differences "
        "may be within normal session-to-session variation.",
        "The candidate session was recorded after the baseline session with the same target sequence, so "
        "practice or familiarity can contribute to any difference (order effect)." if same_seed else
        "The candidate session was recorded after the baseline session, so practice or familiarity can "
        "contribute to any difference (order effect). It used a different seed (same task parameters, "
        "different target sequence); the seeds are not claimed to be equivalent in difficulty.",
    ]
    for analysis, role in ((baseline, "baseline"), (candidate, "candidate")):
        caveats += _session_caveats(analysis, role)
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


# ------------------------------------------------- three-condition comparison
CONDITION_LABELS = {Condition.BASELINE: "Baseline", Condition.STANDARD: "Standard", Condition.CANDIDATE: "Candidate"}
CONDITION_PAIRS = (
    (Condition.BASELINE, Condition.STANDARD),
    (Condition.BASELINE, Condition.CANDIDATE),
    (Condition.STANDARD, Condition.CANDIDATE),
)
CONDITION_CSV_HEADER = [
    "participant_id", "evaluation_id", "task", "condition_order_group", "condition_order",
    "reference_condition", "compared_condition", "reference_session_id", "compared_session_id",
    "reference_condition_position", "compared_condition_position", "reference_seed", "compared_seed",
    "reference_crosshair_id", "compared_crosshair_id", "recommendation_id", "selected_candidate_id",
    "protocol_version", "metric", "unit", "reference", "compared", "difference", "percent_difference",
    "direction", "desirable_direction", "summary",
]


@dataclass
class PairComparison:
    reference_condition: Condition
    compared_condition: Condition
    reference: SessionAnalysis | None
    compared: SessionAnalysis | None
    metrics: list[MetricComparison]

    @property
    def reference_label(self) -> str:
        return CONDITION_LABELS[self.reference_condition]

    @property
    def compared_label(self) -> str:
        return CONDITION_LABELS[self.compared_condition]


@dataclass
class ConditionComparison:
    """Baseline→Standard, Baseline→Candidate and Standard→Candidate for one task of one evaluation cycle."""

    evaluation: ConditionEvaluation
    task: ExperimentType
    analyses: dict[Condition, SessionAnalysis | None]
    pairs: list[PairComparison]
    caveats: list[str] = field(default_factory=list)

    def csv_rows(self) -> list[list]:
        e = self.evaluation
        rows = []
        for pair in self.pairs:
            ref = pair.reference.session if pair.reference else None
            cmp_ = pair.compared.session if pair.compared else None
            for m in pair.metrics:
                rows.append([
                    e.player_id, e.evaluation_id, str(self.task), e.condition_order_group,
                    "-".join(e.condition_order), str(pair.reference_condition), str(pair.compared_condition),
                    ref.session_id if ref else None, cmp_.session_id if cmp_ else None,
                    ref.condition_position if ref else None, cmp_.condition_position if cmp_ else None,
                    ref.random_seed if ref else None, cmp_.random_seed if cmp_ else None,
                    ref.crosshair_id if ref else None, cmp_.crosshair_id if cmp_ else None,
                    e.recommendation_id, e.selected_candidate_id,
                    cmp_.protocol_version if cmp_ else None,
                    m.name, m.definition.unit, m.baseline, m.candidate, m.difference, m.percent_difference,
                    m.direction_text(), m.desirable_direction,
                    m.summary_text(pair.reference_label, pair.compared_label),
                ])
        return rows


def compare_conditions(repo: Repository, evaluation_id: int, task: ExperimentType | str) -> ConditionComparison:
    """Descriptive three-condition comparison (no inferential statistics)."""
    from app.experiment.evaluation import evaluation_sessions, snapshot_differences

    evaluation = repo.get_condition_evaluation(evaluation_id)
    if evaluation is None:
        raise ValidationError(f"Crosshair evaluation {evaluation_id} does not exist")
    task = ExperimentType(task)
    sessions = evaluation_sessions(repo, evaluation)
    analyses: dict[Condition, SessionAnalysis | None] = {}
    for condition in CONDITION_LABELS:
        session = sessions.get(str(condition), {}).get(str(task))
        analyses[condition] = analyze_session(repo, session.session_id) if session else None

    pairs = []
    for reference, compared in CONDITION_PAIRS:
        ref, cmp_ = analyses[reference], analyses[compared]
        pairs.append(PairComparison(reference, compared, ref, cmp_, [
            MetricComparison(name, ref.metrics.get(name) if ref else None,
                             cmp_.metrics.get(name) if cmp_ else None, other_label=str(compared))
            for name in TASK_METRICS[task]
        ]))

    caveats = [
        "Descriptive comparison of single sessions. No statistical test was performed; differences may be "
        "within normal session-to-session variation.",
        f"Baseline was always recorded first. Standard and Candidate were recorded afterwards in the assigned "
        f"order {evaluation.condition_order_group} ({' then '.join(evaluation.condition_order)}), so practice, "
        "fatigue or familiarity can contribute to any difference (order effect).",
        "Standard repeats the baseline crosshair; a Baseline–Standard difference can arise without any "
        "crosshair change (repetition or session-to-session variation).",
        "Each condition used a different seed (same task parameters, different target sequence); the seeds "
        "are not claimed to be equivalent in difficulty.",
        "Practice and familiarization trials are excluded from all metrics.",
    ]
    present = {c: a for c, a in analyses.items() if a is not None}
    for condition in CONDITION_LABELS:
        if condition not in present:
            caveats.append(f"No completed {condition} session for this task in this evaluation yet.")
    for condition, analysis in present.items():
        caveats += _session_caveats(analysis, str(condition))
    if len({a.session.protocol_version for a in present.values()}) > 1:
        caveats.append("The sessions were run under different protocol versions ("
                       + ", ".join(f"{c}: {a.session.protocol_version or 'not recorded'}" for c, a in present.items())
                       + "); task parameters may differ.")
    if len({frozenset(filter(None, _timing_versions(a))) for a in present.values()}) > 1:
        caveats.append("The sessions were recorded with different timing procedures, so their time measures "
                       "are not directly comparable.")
    configs = [_task_config(a) for a in present.values()]
    if any(config != configs[0] for config in configs[1:]):
        caveats.append("Task parameters or the arena size differ between the sessions.")
    standard = present.get(Condition.STANDARD)
    if standard is not None:
        differing = snapshot_differences(evaluation.standard_crosshair_snapshot, standard.session.crosshair_snapshot)
        if differing:
            caveats.append("The Standard session's crosshair snapshot differs from the baseline snapshot ("
                           + ", ".join(differing) + "); Standard and Baseline are not treated as the same crosshair.")
    if any(not (a.session.task_config or {}).get(str(task), {}).get("confirmed", False) for a in present.values()):
        caveats.append("Task parameters are placeholders (confirmed = false).")
    return ConditionComparison(evaluation, task, analyses, pairs, caveats)


def compare_evaluation(repo: Repository, evaluation_id: int) -> list[ConditionComparison]:
    return [compare_conditions(repo, evaluation_id, task) for task in ExperimentType]
