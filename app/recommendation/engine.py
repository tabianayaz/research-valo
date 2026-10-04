"""Rule-based candidate scoring.

This is NOT a validated model and not machine learning. It ranks the
candidate crosshairs in the database with a transparent weighted sum whose
components, weights, thresholds and rules come from
``research_parameters.json`` ("recommendation"). The output is a list of
*candidates to try*; whether any candidate changes performance can only be
measured by the re-test.

Score
    score = sum_c(w_c * component_c) / sum_c(w_c), components in [0, 1].
    w_c = base_weights[c] + sum of ``adjust[c]`` of every rule that fired.

Components (computed from the crosshair parameters and the experiment
background; normalisation constants are configurable)
    visibility        WCAG contrast ratio of the line colour (blended with its
                      opacity over the background) and, if enabled, of the
                      black outline; the larger one, mapped 1 -> 0 and
                      ``contrast_ratio_full`` -> 1.
    center_precision  1 - (gap + thickness / 2) / center_offset_full_px
                      (distance from the centre to the inner edge region).
    low_occlusion     1 - (gap + size + outline) / extent_full_px
                      (how far the crosshair extends from the centre).
    source_fidelity   ``fidelity_scores`` of the mapping from the source code.

Rules
    ``{"metric": "<task>.<metric>", "op": ">" | "<", "threshold": x,
    "adjust": {component: delta}}``. A rule fires when the player's profile
    value satisfies the comparison; rules whose metric is missing are
    reported as "no data" and do not fire.

Candidate pool
    All crosshairs with role ``candidate``. Crosshairs identical to the
    baseline are excluded (nothing to compare); identical parameter sets are
    collapsed to the lowest crosshair id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.analysis.metrics import METRICS, format_metric
from app.analysis.profile import PlayerProfile
from app.config.research import ResearchParameters
from app.crosshair.config import CrosshairConfig
from app.data.models import CrosshairRecord, CrosshairRole
from app.data.repository import Repository, crosshair_config_hash
from app.utils.validators import ValidationError

COMPONENTS = ("visibility", "center_precision", "low_occlusion", "source_fidelity")
COMPONENT_LABELS = {
    "visibility": "visibility",
    "center_precision": "centre precision",
    "low_occlusion": "low occlusion",
    "source_fidelity": "source fidelity",
}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    metric: str
    op: str
    threshold: float
    adjust: dict[str, float]
    rationale: str


@dataclass(frozen=True)
class RecommendationConfig:
    confirmed: bool
    method: str
    method_version: str
    top_n: int
    base_weights: dict[str, float]
    fidelity_scores: dict[str, float]
    contrast_ratio_full: float
    center_offset_full_px: float
    extent_full_px: float
    rules: tuple[Rule, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecommendationConfig:
        try:
            norm = data["normalisation"]
            config = cls(
                confirmed=bool(data["confirmed"]),
                method=str(data["method"]),
                method_version=str(data["method_version"]),
                top_n=int(data["top_n"]),
                base_weights={k: float(v) for k, v in data["base_weights"].items()},
                fidelity_scores={k: float(v) for k, v in data["fidelity_scores"].items()},
                contrast_ratio_full=float(norm["contrast_ratio_full"]),
                center_offset_full_px=float(norm["center_offset_full_px"]),
                extent_full_px=float(norm["extent_full_px"]),
                rules=tuple(
                    Rule(str(r["id"]), str(r["metric"]), str(r["op"]), float(r["threshold"]),
                         {k: float(v) for k, v in r["adjust"].items()}, str(r.get("rationale", "")))
                    for r in data["rules"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"Invalid recommendation parameters: {exc}") from exc
        problems = []
        if set(config.base_weights) != set(COMPONENTS):
            problems.append(f"base_weights must define exactly {', '.join(COMPONENTS)}")
        if any(w < 0 for w in config.base_weights.values()):
            problems.append("base_weights must be >= 0")
        if config.top_n < 1:
            problems.append("top_n must be >= 1")
        if config.contrast_ratio_full <= 1 or config.center_offset_full_px <= 0 or config.extent_full_px <= 0:
            problems.append("normalisation values must be positive (contrast_ratio_full > 1)")
        for rule in config.rules:
            task, _, metric = rule.metric.partition(".")
            if task not in ("flick", "tracking", "switching") or metric not in METRICS:
                problems.append(f"rule {rule.rule_id}: unknown metric {rule.metric}")
            if rule.op not in (">", "<"):
                problems.append(f"rule {rule.rule_id}: op must be '>' or '<'")
            if not set(rule.adjust) <= set(COMPONENTS):
                problems.append(f"rule {rule.rule_id}: unknown component in adjust")
        if problems:
            raise ValidationError("Invalid recommendation parameters: " + "; ".join(problems))
        return config


# ---------------------------------------------------------------- components
def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def blended_contrast(color: str, opacity: float, background: str) -> float:
    """WCAG contrast ratio of ``color`` drawn at ``opacity`` over ``background``."""
    fg, bg = _rgb(color), _rgb(background)
    mixed = tuple(opacity * f + (1 - opacity) * b for f, b in zip(fg, bg))
    l1, l2 = sorted((_luminance(mixed), _luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def component_scores(
    crosshair: CrosshairConfig, fidelity: str | None, config: RecommendationConfig,
    background: str, px_per_unit: float,
) -> dict[str, float]:
    contrast = blended_contrast(crosshair.color, crosshair.opacity, background)
    if crosshair.outline_enabled:
        contrast = max(contrast, blended_contrast("#000000", crosshair.opacity, background))
    gap = crosshair.gap * px_per_unit
    thickness = crosshair.thickness * px_per_unit
    extent = (crosshair.gap + crosshair.size
              + (crosshair.outline_thickness if crosshair.outline_enabled else 0)) * px_per_unit
    return {
        "visibility": _clip((contrast - 1) / (config.contrast_ratio_full - 1)),
        "center_precision": _clip(1 - (gap + thickness / 2) / config.center_offset_full_px),
        "low_occlusion": _clip(1 - extent / config.extent_full_px),
        "source_fidelity": config.fidelity_scores.get(fidelity or "", 0.0),
    }


# --------------------------------------------------------------------- rules
@dataclass
class RuleOutcome:
    rule: Rule
    value: float | None
    fired: bool

    @property
    def status(self) -> str:
        if self.value is None:
            return "no data"
        return "applied" if self.fired else "not applied"

    def describe(self) -> str:
        _, _, metric = self.rule.metric.partition(".")
        shown = format_metric(metric, self.value) if self.value is not None else "no data"
        threshold = format_metric(metric, self.rule.threshold)
        return f"{METRICS[metric].label} {shown} {self.rule.op} {threshold}"


def evaluate_rules(profile: PlayerProfile, config: RecommendationConfig) -> list[RuleOutcome]:
    outcomes = []
    for rule in config.rules:
        value = profile.value(rule.metric)
        fired = value is not None and (value > rule.threshold if rule.op == ">" else value < rule.threshold)
        outcomes.append(RuleOutcome(rule, value, fired))
    return outcomes


def effective_weights(outcomes: list[RuleOutcome], config: RecommendationConfig) -> dict[str, float]:
    weights = dict(config.base_weights)
    for outcome in outcomes:
        if outcome.fired:
            for component, delta in outcome.rule.adjust.items():
                weights[component] = max(0.0, weights[component] + delta)
    return weights


# ------------------------------------------------------------------- scoring
@dataclass
class ScoredCandidate:
    crosshair: CrosshairRecord
    components: dict[str, float]
    score: float
    rank: int = 0
    source_player: str | None = None
    explanation: str = ""


@dataclass
class RecommendationResult:
    profile: PlayerProfile
    config: RecommendationConfig
    outcomes: list[RuleOutcome]
    weights: dict[str, float]
    ranked: list[ScoredCandidate]
    pool_size: int
    excluded: list[str] = field(default_factory=list)

    @property
    def top(self) -> list[ScoredCandidate]:
        return self.ranked[: self.config.top_n]


def candidate_pool(repo: Repository, baseline: CrosshairRecord) -> tuple[list[CrosshairRecord], list[str]]:
    baseline_hash = crosshair_config_hash(baseline)
    seen: dict[str, int] = {}
    pool, excluded = [], []
    for record in sorted(repo.list_crosshairs(CrosshairRole.CANDIDATE), key=lambda r: r.crosshair_id):
        digest = crosshair_config_hash(record)
        if digest == baseline_hash:
            excluded.append(f"{record.name} (#{record.crosshair_id}): identical to the baseline")
        elif digest in seen:
            excluded.append(f"{record.name} (#{record.crosshair_id}): same parameters as #{seen[digest]}")
        else:
            seen[digest] = record.crosshair_id
            pool.append(record)
    return pool, excluded


def explain(candidate: ScoredCandidate, weights: dict[str, float], outcomes: list[RuleOutcome]) -> str:
    parts = [
        f"{COMPONENT_LABELS[c]} {candidate.components[c]:.2f} (weight {weights[c]:g})" for c in COMPONENTS
    ]
    fired = [o for o in outcomes if o.fired]
    text = f"Score {candidate.score:.3f} = weighted mean of " + ", ".join(parts) + "."
    if fired:
        text += " Rules that changed the weights: " + "; ".join(
            f"{o.rule.rule_id} ({o.describe()})" for o in fired) + "."
    else:
        text += " No rule changed the base weights."
    return text


def score_candidates(
    repo: Repository, research: ResearchParameters, baseline: CrosshairRecord, profile: PlayerProfile,
) -> RecommendationResult:
    config = RecommendationConfig.from_dict(research.recommendation)
    outcomes = evaluate_rules(profile, config)
    weights = effective_weights(outcomes, config)
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValidationError("All recommendation weights are zero")
    sources = {listing.crosshair.crosshair_id: listing.source.source_player
               for listing in repo.list_source_listings() if listing.crosshair}

    pool, excluded = candidate_pool(repo, baseline)
    scored = []
    for record in pool:
        components = component_scores(CrosshairConfig.from_record(record), record.fidelity, config,
                                      research.experiment_background_color, research.px_per_unit)
        score = sum(weights[c] * components[c] for c in COMPONENTS) / total_weight
        scored.append(ScoredCandidate(record, components, round(score, 6),
                                      source_player=sources.get(record.crosshair_id)))
    scored.sort(key=lambda c: (-c.score, c.crosshair.crosshair_id))
    for rank, candidate in enumerate(scored, start=1):
        candidate.rank = rank
        candidate.explanation = explain(candidate, weights, outcomes)
    return RecommendationResult(profile, config, outcomes, weights, scored, len(pool), excluded)


def store_recommendation(repo: Repository, result: RecommendationResult) -> int:
    config = result.config
    return repo.add_recommendation(
        player_id=result.profile.player_id,
        method=config.method,
        method_version=config.method_version,
        weights={
            "effective": result.weights,
            "base": config.base_weights,
            "confirmed": config.confirmed,
            "rules": [
                {"id": o.rule.rule_id, "metric": o.rule.metric, "op": o.rule.op,
                 "threshold": o.rule.threshold, "adjust": o.rule.adjust,
                 "value": o.value, "status": o.status}
                for o in result.outcomes
            ],
            "normalisation": {
                "contrast_ratio_full": config.contrast_ratio_full,
                "center_offset_full_px": config.center_offset_full_px,
                "extent_full_px": config.extent_full_px,
            },
            "fidelity_scores": config.fidelity_scores,
            "pool_size": result.pool_size,
            "excluded": result.excluded,
        },
        profile=result.profile.to_dict(),
        source_session_ids=result.profile.source_session_ids,
        candidates=[
            {"crosshair_id": c.crosshair.crosshair_id, "rank": c.rank, "score": c.score,
             "component_scores": c.components, "explanation": c.explanation}
            for c in result.top
        ],
    )
