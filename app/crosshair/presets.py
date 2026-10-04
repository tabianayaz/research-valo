"""Standard (baseline) crosshair, defined in research_parameters.json."""

from __future__ import annotations

from app.config.research import ResearchParameters
from app.crosshair.config import FIELDS, CrosshairConfig
from app.data.models import CrosshairRecord, CrosshairRole
from app.data.repository import Repository, crosshair_config_hash
from app.utils.logging import get_logger

log = get_logger("crosshair.presets")


def baseline_config(params: ResearchParameters) -> CrosshairConfig:
    data = {k: params.baseline_crosshair[k] for k in FIELDS}
    return CrosshairConfig.from_dict(data).validated(params.parameter_ranges)


def baseline_name(params: ResearchParameters) -> str:
    return str(params.baseline_crosshair.get("name", "Standard crosshair (baseline)"))


def ensure_baseline(repo: Repository, params: ResearchParameters) -> CrosshairRecord:
    """Return the baseline row matching the current parameters, creating it if needed.

    If the configured baseline changes, a *new* row is created; earlier sessions
    keep referencing the baseline they actually used.
    """
    config = baseline_config(params)
    record = config.to_record(baseline_name(params), CrosshairRole.BASELINE)
    existing = repo.find_crosshair_by_hash(crosshair_config_hash(record), CrosshairRole.BASELINE)
    if existing is not None:
        return existing
    log.info("baseline_created config=%s", config.to_json())
    return repo.add_crosshair(record)
