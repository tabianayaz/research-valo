"""Crosshair-specific reusable widgets (preview panel, parameter list, thumbnails)."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout, QWidget

from app.config.research import ResearchParameters
from app.crosshair.config import CrosshairConfig
from app.crosshair.renderer import CrosshairPreview, render_pixmap
from app.crosshair.shape import CrosshairShape
from app.i18n import set_tr_text, tr
from app.ui.components import label

PREVIEW_ZOOM = 6
PREVIEW_MAX_HEIGHT = 300
THUMBNAIL_SIZE = QSize(112, 112)
THUMBNAIL_ZOOM = 1


class PreviewPanel(QWidget):
    """Side-by-side actual-size and magnified preview on the experiment background."""

    def __init__(self, research: ResearchParameters, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        background = research.experiment_background_color
        self.actual = CrosshairPreview(research.px_per_unit, background, zoom=1,
                                       minimum=QSize(200, 200))
        self.zoomed = CrosshairPreview(research.px_per_unit, background, zoom=PREVIEW_ZOOM,
                                       minimum=QSize(200, 200))
        for widget, caption, values in (
            (self.actual, "Actual size (1 unit = {px} physical px)",
             {"px": format(research.px_per_unit, "g")}),
            (self.zoomed, "Magnified ×{zoom} (inspection only)", {"zoom": PREVIEW_ZOOM}),
        ):
            widget.setMaximumHeight(PREVIEW_MAX_HEIGHT)
            column = QVBoxLayout()
            column.setSpacing(6)
            column.addWidget(widget, 1)
            caption_label = label("", "faintLabel")
            set_tr_text(caption_label, caption, **values)
            column.addWidget(caption_label)
            column.addStretch(1)
            layout.addLayout(column, 1)

    def set_shape(self, shape: CrosshairShape | None) -> None:
        self.actual.set_shape(shape)
        self.zoomed.set_shape(shape)


def parameter_rows(config: CrosshairConfig) -> list[tuple[str, str]]:
    return [
        ("Color", config.color),
        ("Size (arm length)", f"{config.size:g}"),
        ("Thickness", f"{config.thickness:g}"),
        ("Gap (center to arm)", f"{config.gap:g}"),
        ("Outline", tr("On") if config.outline_enabled else tr("Off")),
        ("Outline thickness", f"{config.outline_thickness:g}" if config.outline_enabled else "–"),
        ("Opacity", f"{config.opacity:g}"),
    ]


class ParameterList(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setHorizontalSpacing(24)
        self.form.setVerticalSpacing(6)

    def set_config(self, config: CrosshairConfig) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        for name, value in parameter_rows(config):
            self.form.addRow(label(name, "mutedLabel"), label(value))


def thumbnail(shape: CrosshairShape | None, research: ResearchParameters,
              device_pixel_ratio: float = 1.0) -> QPixmap | None:
    if shape is None:
        return None
    return render_pixmap(shape, THUMBNAIL_SIZE, research.experiment_background_color,
                         research.px_per_unit, THUMBNAIL_ZOOM, device_pixel_ratio)
