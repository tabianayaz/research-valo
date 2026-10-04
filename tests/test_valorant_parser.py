from __future__ import annotations

from pathlib import Path

import pytest

from app.crosshair.mapping import Fidelity, map_valorant_profile
from app.data.models import CrosshairRole
from app.data.repository import Repository
from app.scraper.importer import ImportStatus, Provenance, import_valorant_codes
from app.scraper.parsers import CrosshairCodeError, parse_valorant_code, resolve_primary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROVIDED_CODES = PROJECT_ROOT / "assets" / "crosshair_sources" / "researcher_provided_valorant_codes.txt"
RANGES = {"size": (1, 20), "thickness": (1, 10), "gap": (0, 20),
          "outline_thickness": (1, 6), "opacity": (0.05, 1.0)}


def mapped(code: str):
    parsed = parse_valorant_code(code)
    profile = resolve_primary(parsed)
    return parsed, profile, map_valorant_profile(parsed, profile)


def test_sections_and_general_options() -> None:
    parsed = parse_valorant_code("0;s;1;P;c;5;0l;4;S;d;0")
    assert parsed.general == {"s": "1"}
    assert parsed.sections["primary"] == {"c": "5", "0l": "4"}
    assert parsed.sections["sniper"] == {"d": "0"}


def test_defaults_applied_for_missing_keys() -> None:
    _, profile, _ = mapped("0;P;0l;4")
    assert profile.inner_length == 4
    assert profile.inner_offset == 3          # default
    assert profile.inner_opacity == 0.8       # default
    assert profile.flag("outline_enabled")    # default on
    assert profile.color_hex == "#FFFFFF"


def test_simple_cross_is_exact() -> None:
    _, profile, result = mapped("0;s;1;P;c;5;h;0;m;1;0l;4;0o;2;0a;1;0f;0;1b;0")
    assert result.fidelity == Fidelity.EXACT
    c = result.config
    assert (c.color, c.size, c.thickness, c.gap, c.outline_enabled, c.opacity) == (
        "#00FFFF", 4, 2, 2, False, 1.0)
    assert profile.uninterpreted == {"m": "1"}


def test_dot_only_is_not_representable() -> None:
    _, _, result = mapped("0;P;c;1;o;1;d;1;0b;0;1b;0")
    assert result.fidelity == Fidelity.NOT_REPRESENTABLE
    assert result.config is None
    assert "center dot" in result.differences[0]


@pytest.mark.parametrize("code", [
    "0;P;0l;0;0v;3;0g;1;1b;0",        # vertical-only
    "0;P;0l;14;0v;0;0g;1;1b;0",       # horizontal-only
])
def test_single_axis_lines_not_representable(code: str) -> None:
    assert mapped(code)[2].fidelity == Fidelity.NOT_REPRESENTABLE


def test_outer_lines_and_dot_make_mapping_approximate() -> None:
    _, _, result = mapped("0;P;h;0;d;1;0l;3;0o;1;0a;1;1l;2;1o;6;1a;1")
    assert result.fidelity == Fidelity.APPROXIMATE
    assert any("Center dot" in d for d in result.differences)
    assert any("Outer lines" in d for d in result.differences)


def test_outline_opacity_difference_reported() -> None:
    _, _, result = mapped("0;P;h;1;o;0.5;0a;1;1b;0")
    assert result.fidelity == Fidelity.APPROXIMATE
    assert result.config.outline_enabled


def test_custom_color_with_alpha() -> None:
    _, profile, _ = mapped("0;P;c;8;u;D0021BFF;1b;0")
    assert profile.color_hex == "#D0021B"
    assert profile.warnings == []
    _, profile, _ = mapped("0;P;c;8;u;F28D9F80;1b;0")
    assert any("alpha" in w for w in profile.warnings)


def test_custom_color_without_index_uses_preset_and_warns() -> None:
    _, profile, _ = mapped("0;P;u;FC5A8DFF;1b;0")
    assert profile.color_hex == "#FFFFFF"
    assert profile.warnings


def test_missing_trailing_value_warns_and_uses_default() -> None:
    parsed, profile, _ = mapped("0;P;o;0;0t;1;0l;2;0o;0;0a;1;0f;0;1b;")
    assert any("'1b'" in w for w in parsed.warnings)
    assert profile.flag("outer_enabled")  # default


def test_out_of_range_values_are_clamped_with_warning() -> None:
    _, profile, _ = mapped("0;P;0l;50")
    assert profile.inner_length == 20
    assert profile.warnings


@pytest.mark.parametrize("bad", ["", "   ", "P;0l;4", "0;0l;4", "0;P;0l;4;!!;1", "0;P;toolong;1"])
def test_unparseable_codes_raise(bad: str) -> None:
    with pytest.raises(CrosshairCodeError):
        resolve_primary(parse_valorant_code(bad))


def test_original_shape_includes_dot_and_outer_lines() -> None:
    _, profile, _ = mapped("0;P;d;1;0l;3;1l;2")
    shape = profile.to_shape()
    assert shape.dot is not None
    assert len(shape.line_sets) == 2


def test_import_provided_codes(repo: Repository) -> None:
    lines = PROVIDED_CODES.read_text(encoding="utf-8").splitlines()
    outcomes = import_valorant_codes(repo, lines, Provenance("Researcher-provided list"), RANGES)
    statuses = [o.status for o in outcomes]
    assert len(outcomes) == 17
    assert ImportStatus.INVALID not in statuses
    assert statuses.count(ImportStatus.DUPLICATE) == 1
    candidates = repo.list_crosshairs(CrosshairRole.CANDIDATE)
    assert len(candidates) == statuses.count(ImportStatus.IMPORTED)
    listings = repo.list_source_listings()
    assert len(listings) == 16
    assert all(l.source.raw_payload["mapping"]["fidelity"] for l in listings)

    again = import_valorant_codes(repo, lines, Provenance("Researcher-provided list"), RANGES)
    assert all(o.status == ImportStatus.DUPLICATE for o in again)


def test_invalid_code_is_reported_not_stored(repo: Repository) -> None:
    outcomes = import_valorant_codes(repo, ["garbage"], Provenance("t"), RANGES)
    assert outcomes[0].status == ImportStatus.INVALID
    assert repo.list_source_listings() == []
