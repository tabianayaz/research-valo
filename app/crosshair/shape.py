"""Pure-Python crosshair geometry (no Qt), shared by every crosshair model.

Geometry rules (deterministic, in physical/device pixels):

* The crosshair center is a pixel *boundary* point (0, 0). The renderer maps it
  to ``floor(widget_size_px / 2)``.
* A length/offset/thickness of ``u`` units becomes ``floor(u * px_per_unit + 0.5)``
  pixels (round half up; Python's ``round`` is not used because it rounds half
  to even).
* A line of thickness ``t`` px spans ``[-t//2, -t//2 + t)`` across its axis, so an
  odd thickness extends one pixel further to the bottom/right of the center.
* Horizontal arms span ``[offset, offset + length)`` on each side of the center;
  vertical arms likewise.
* A center dot of size ``z`` px spans ``[-z//2, -z//2 + z)`` on both axes.
* The outline is the union of every element expanded by the outline thickness,
  minus the union of the filled elements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Rect = tuple[int, int, int, int]  # x, y, width, height relative to the center point


@dataclass(frozen=True)
class LineSet:
    offset: float
    length_h: float
    length_v: float
    thickness: float
    opacity: float


@dataclass(frozen=True)
class Dot:
    size: float
    opacity: float


@dataclass(frozen=True)
class Outline:
    thickness: float
    opacity: float


@dataclass(frozen=True)
class CrosshairShape:
    color: str
    line_sets: tuple[LineSet, ...] = ()
    dot: Dot | None = None
    outline: Outline | None = None


@dataclass(frozen=True)
class FillLayer:
    rects: tuple[Rect, ...]
    opacity: float


@dataclass(frozen=True)
class ShapeGeometry:
    fill_layers: tuple[FillLayer, ...]
    outline_rects: tuple[Rect, ...]
    outline_thickness_px: int
    outline_opacity: float

    def all_fill_rects(self) -> list[Rect]:
        return [r for layer in self.fill_layers for r in layer.rects]

    def is_visible(self) -> bool:
        return any(layer.rects and layer.opacity > 0 for layer in self.fill_layers)

    def bounding_box(self) -> Rect | None:
        rects = self.all_fill_rects()
        if self.outline_thickness_px > 0:
            rects = rects + list(self.outline_rects)
        if not rects:
            return None
        left = min(r[0] for r in rects)
        top = min(r[1] for r in rects)
        right = max(r[0] + r[2] for r in rects)
        bottom = max(r[1] + r[3] for r in rects)
        return (left, top, right - left, bottom - top)


def units_to_px(units: float, px_per_unit: float) -> int:
    return int(math.floor(units * px_per_unit + 0.5))


def line_set_rects(line_set: LineSet, px_per_unit: float) -> list[Rect]:
    offset = units_to_px(line_set.offset, px_per_unit)
    length_h = units_to_px(line_set.length_h, px_per_unit)
    length_v = units_to_px(line_set.length_v, px_per_unit)
    thickness = units_to_px(line_set.thickness, px_per_unit)
    if thickness <= 0:
        return []
    start = -(thickness // 2)
    rects: list[Rect] = []
    if length_h > 0:
        rects.append((offset, start, length_h, thickness))
        rects.append((-offset - length_h, start, length_h, thickness))
    if length_v > 0:
        rects.append((start, offset, thickness, length_v))
        rects.append((start, -offset - length_v, thickness, length_v))
    return rects


def dot_rect(dot: Dot, px_per_unit: float) -> Rect | None:
    size = units_to_px(dot.size, px_per_unit)
    if size <= 0:
        return None
    start = -(size // 2)
    return (start, start, size, size)


def expand(rect: Rect, by: int) -> Rect:
    x, y, w, h = rect
    return (x - by, y - by, w + 2 * by, h + 2 * by)


def compute_geometry(shape: CrosshairShape, px_per_unit: float) -> ShapeGeometry:
    layers: list[FillLayer] = []
    for line_set in shape.line_sets:
        rects = line_set_rects(line_set, px_per_unit)
        if rects and line_set.opacity > 0:
            layers.append(FillLayer(tuple(rects), line_set.opacity))
    if shape.dot is not None and shape.dot.opacity > 0:
        rect = dot_rect(shape.dot, px_per_unit)
        if rect is not None:
            layers.append(FillLayer((rect,), shape.dot.opacity))

    outline_px = 0
    outline_opacity = 0.0
    outline_rects: tuple[Rect, ...] = ()
    if shape.outline is not None and shape.outline.opacity > 0:
        outline_px = units_to_px(shape.outline.thickness, px_per_unit)
        if outline_px > 0:
            outline_opacity = shape.outline.opacity
            outline_rects = tuple(
                expand(r, outline_px) for layer in layers for r in layer.rects
            )
    return ShapeGeometry(tuple(layers), outline_rects, outline_px, outline_opacity)
