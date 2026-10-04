from __future__ import annotations

from app.crosshair.config import CrosshairConfig
from app.crosshair.shape import (
    CrosshairShape,
    Dot,
    LineSet,
    compute_geometry,
    line_set_rects,
    units_to_px,
)


def covered_pixels(rects) -> set[tuple[int, int]]:
    return {(x + i, y + j) for x, y, w, h in rects for i in range(w) for j in range(h)}


def test_units_round_half_up() -> None:
    assert units_to_px(2.5, 1.0) == 3
    assert units_to_px(3.5, 1.0) == 4
    assert units_to_px(1, 1.5) == 2
    assert units_to_px(0.4, 1.0) == 0


def test_cross_arms_positions() -> None:
    rects = line_set_rects(LineSet(offset=2, length_h=4, length_v=4, thickness=2, opacity=1), 1.0)
    assert sorted(rects) == sorted([
        (2, -1, 4, 2), (-6, -1, 4, 2),   # right, left
        (-1, 2, 2, 4), (-1, -6, 2, 4),   # down, up
    ])


def test_odd_thickness_extends_bottom_right() -> None:
    rects = line_set_rects(LineSet(0, 3, 3, 1, 1), 1.0)
    assert (0, 0, 3, 1) in rects  # right arm occupies row y=0 only


def test_zero_gap_arms_meet_without_gaps() -> None:
    pixels = covered_pixels(line_set_rects(LineSet(0, 2, 2, 2, 1), 1.0))
    assert {(-1, -1), (0, 0), (-1, 0), (0, -1)} <= pixels


def test_px_per_unit_scales_geometry() -> None:
    config = CrosshairConfig("#FFFFFF", 4, 2, 2, False, 1, 1.0)
    one = compute_geometry(config.to_shape(), 1.0).bounding_box()
    two = compute_geometry(config.to_shape(), 2.0).bounding_box()
    assert one == (-6, -6, 12, 12)
    assert two == (-12, -12, 24, 24)


def test_outline_expands_bounding_box() -> None:
    plain = CrosshairConfig("#FFFFFF", 4, 2, 2, False, 1, 1.0).to_shape()
    outlined = CrosshairConfig("#FFFFFF", 4, 2, 2, True, 1, 1.0).to_shape()
    assert compute_geometry(outlined, 1.0).bounding_box() == (-7, -7, 14, 14)
    assert compute_geometry(plain, 1.0).outline_thickness_px == 0


def test_dot_only_shape() -> None:
    geometry = compute_geometry(CrosshairShape("#FFFFFF", dot=Dot(2, 1.0)), 1.0)
    assert geometry.all_fill_rects() == [(-1, -1, 2, 2)]
    assert geometry.is_visible()


def test_geometry_is_deterministic() -> None:
    shape = CrosshairConfig("#FFFFFF", 5, 3, 1, True, 2, 0.7).to_shape()
    assert compute_geometry(shape, 1.25) == compute_geometry(shape, 1.25)
