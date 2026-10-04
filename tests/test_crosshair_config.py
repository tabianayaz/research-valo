from __future__ import annotations

import pytest

from app.config.research import load_research_parameters
from app.crosshair.config import CrosshairConfig
from app.crosshair.presets import baseline_config, ensure_baseline
from app.data.models import CrosshairRole
from app.data.repository import Repository
from app.utils.validators import ValidationError

RANGES = {
    "size": (1, 20),
    "thickness": (1, 10),
    "gap": (0, 20),
    "outline_thickness": (1, 6),
    "opacity": (0.05, 1.0),
}


def make(**overrides) -> CrosshairConfig:
    values = dict(color="#00FFFF", size=4, thickness=2, gap=2, outline_enabled=False,
                  outline_thickness=1, opacity=1.0)
    values.update(overrides)
    return CrosshairConfig(**values)


def test_valid_config_has_no_errors() -> None:
    assert make().errors(RANGES) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"color": "cyan"},
        {"color": "#12345"},
        {"size": 0},
        {"size": 21},
        {"thickness": 0},
        {"gap": -1},
        {"opacity": 0},
        {"opacity": 1.5},
        {"outline_thickness": 7},
        {"size": float("nan")},
        {"outline_enabled": 1},
    ],
)
def test_invalid_values_rejected(overrides) -> None:
    config = make(**overrides)
    assert config.errors(RANGES)
    with pytest.raises(ValidationError):
        config.validated(RANGES)


def test_json_roundtrip() -> None:
    config = make(color="#d0021b", outline_enabled=True)
    restored = CrosshairConfig.from_json(config.to_json())
    assert restored == make(color="#D0021B", outline_enabled=True)


@pytest.mark.parametrize(
    "payload",
    [
        '{"color": "#FFFFFF"}',
        "not json",
        '{"color": "#FFFFFF", "size": "big", "thickness": 2, "gap": 1, '
        '"outline_enabled": false, "outline_thickness": 1, "opacity": 1}',
        '{"color": "#FFFFFF", "size": 4, "thickness": 2, "gap": 1, '
        '"outline_enabled": "yes", "outline_thickness": 1, "opacity": 1}',
    ],
)
def test_malformed_json_rejected(payload: str) -> None:
    with pytest.raises(ValidationError):
        CrosshairConfig.from_json(payload)


def test_record_roundtrip(repo: Repository) -> None:
    config = make(outline_enabled=True, outline_thickness=2)
    record = repo.add_crosshair(config.to_record("test", CrosshairRole.CUSTOM))
    assert CrosshairConfig.from_record(repo.get_crosshair(record.crosshair_id)) == config


def test_baseline_from_research_parameters_is_valid() -> None:
    params = load_research_parameters()
    assert baseline_config(params).errors(params.parameter_ranges) == []


def test_ensure_baseline_is_idempotent(repo: Repository) -> None:
    params = load_research_parameters()
    first = ensure_baseline(repo, params)
    second = ensure_baseline(repo, params)
    assert first.crosshair_id == second.crosshair_id
    assert len(repo.list_crosshairs(CrosshairRole.BASELINE)) == 1
