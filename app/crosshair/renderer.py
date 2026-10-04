"""QPainter rendering of crosshair shapes with exact device-pixel geometry."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.crosshair.shape import CrosshairShape, Rect, compute_geometry

OUTLINE_COLOR = "#000000"


def _region(rects: list[Rect] | tuple[Rect, ...], center: QPoint, zoom: int) -> QRegion:
    region = QRegion()
    for x, y, w, h in rects:
        region = region.united(
            QRegion(QRect(center.x() + x * zoom, center.y() + y * zoom, w * zoom, h * zoom))
        )
    return region


def _fill_region(painter: QPainter, region: QRegion, color: QColor) -> None:
    for rect in region:
        painter.fillRect(rect, color)


def paint_shape(
    painter: QPainter,
    shape: CrosshairShape,
    center_device_px: QPoint,
    px_per_unit: float,
    device_pixel_ratio: float = 1.0,
    zoom: int = 1,
) -> None:
    """Paint ``shape`` centred on a device-pixel boundary point.

    ``zoom`` (integer) magnifies every device pixel into a zoom×zoom block for
    inspection; it never changes the underlying geometry.
    """
    geometry = compute_geometry(shape, px_per_unit)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.scale(1.0 / device_pixel_ratio, 1.0 / device_pixel_ratio)

    fill_union = _region(geometry.all_fill_rects(), center_device_px, zoom)
    if geometry.outline_thickness_px > 0:
        outline = _region(geometry.outline_rects, center_device_px, zoom).subtracted(fill_union)
        color = QColor(OUTLINE_COLOR)
        color.setAlphaF(geometry.outline_opacity)
        _fill_region(painter, outline, color)

    for layer in geometry.fill_layers:
        color = QColor(shape.color)
        color.setAlphaF(layer.opacity)
        _fill_region(painter, _region(layer.rects, center_device_px, zoom), color)
    painter.restore()


def render_pixmap(
    shape: CrosshairShape,
    size: QSize,
    background: str,
    px_per_unit: float,
    zoom: int = 1,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    pixmap = QPixmap(round(size.width() * device_pixel_ratio), round(size.height() * device_pixel_ratio))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(QColor(background))
    painter = QPainter(pixmap)
    center = QPoint(pixmap.width() // 2, pixmap.height() // 2)
    paint_shape(painter, shape, center, px_per_unit, device_pixel_ratio, zoom)
    painter.end()
    return pixmap


class CrosshairPreview(QWidget):
    """Shows a crosshair on the experiment background at exact pixel size (or zoomed)."""

    def __init__(
        self,
        px_per_unit: float,
        background: str,
        zoom: int = 1,
        minimum: QSize = QSize(160, 160),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._shape: CrosshairShape | None = None
        self._px_per_unit = px_per_unit
        self._background = background
        self._zoom = zoom
        self.setMinimumSize(minimum)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def set_shape(self, shape: CrosshairShape | None) -> None:
        self._shape = shape
        self.update()

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(1, int(zoom))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._background))
        if self._shape is not None:
            dpr = self.devicePixelRatioF()
            center = QPoint(int(self.width() * dpr) // 2, int(self.height() * dpr) // 2)
            paint_shape(painter, self._shape, center, self._px_per_unit, dpr, self._zoom)
        painter.end()
