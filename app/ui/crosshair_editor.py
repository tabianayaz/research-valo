"""Crosshair settings editor with immediate preview and validation."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Signal
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.crosshair.validator import normalize_hex_color
from app.data.models import CrosshairRole
from app.i18n import display, tr, tr_message
from app.ui.components import Banner, Card, hbox, label, primary_button, secondary_button
from app.ui.crosshair_widgets import PreviewPanel
from app.utils.logging import get_logger

log = get_logger("ui.crosshair_editor")


class CrosshairEditor(QWidget):
    saved = Signal(int)  # crosshair_id

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        ranges = context.research.parameter_ranges
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        settings = Card("Settings")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        self.color_edit = QLineEdit()
        self.color_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"#?[0-9A-Fa-f]{0,6}"))
        )
        self.color_swatch = QPushButton()
        self.color_swatch.setObjectName("colorSwatch")
        self.color_swatch.setToolTip(tr("Choose colour"))
        self.color_swatch.clicked.connect(self._pick_color)
        color_row = QHBoxLayout()
        color_row.addWidget(self.color_swatch)
        color_row.addWidget(self.color_edit, 1)
        form.addRow("Color", color_row)

        self.size_spin = self._int_spin(ranges["size"])
        self.thickness_spin = self._int_spin(ranges["thickness"])
        self.gap_spin = self._int_spin(ranges["gap"])
        self.outline_check = QCheckBox(tr("Enabled"))
        self.outline_thickness_spin = self._int_spin(ranges["outline_thickness"])
        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setDecimals(3)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setRange(*ranges["opacity"])

        form.addRow("Size", self._with_range(self.size_spin, ranges["size"]))
        form.addRow("Thickness", self._with_range(self.thickness_spin, ranges["thickness"]))
        form.addRow("Gap", self._with_range(self.gap_spin, ranges["gap"]))
        form.addRow("Outline", self.outline_check)
        form.addRow("Outline thickness",
                    self._with_range(self.outline_thickness_spin, ranges["outline_thickness"]))
        form.addRow("Opacity", self._with_range(self.opacity_spin, ranges["opacity"]))
        settings.body.addLayout(form)

        self.banner = Banner()
        settings.body.addWidget(self.banner)

        self.load_combo = QComboBox()
        self.load_combo.setMinimumWidth(220)
        load_button = secondary_button("Load")
        load_button.clicked.connect(self._load_selected)
        reset_button = secondary_button("Reset to standard")
        reset_button.clicked.connect(self.reset_to_baseline)
        settings.body.addWidget(label("Load an existing crosshair", "faintLabel"))
        load_row = QHBoxLayout()
        load_row.addWidget(self.load_combo, 1)
        load_row.addWidget(load_button)
        settings.body.addLayout(load_row)
        settings.body.addLayout(hbox(reset_button))

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("Name for this custom crosshair"))
        self.save_button = primary_button("Save as custom crosshair")
        self.save_button.clicked.connect(self._save)
        settings.body.addSpacing(6)
        settings.body.addWidget(self.name_edit)
        settings.body.addLayout(hbox(self.save_button))
        settings.body.addStretch(1)
        settings.setMinimumWidth(380)
        layout.addWidget(settings, 0)

        preview_card = Card("Preview")
        self.preview = PreviewPanel(context.research)
        preview_card.body.addWidget(self.preview, 1)
        preview_card.body.addWidget(
            label(
                "The outline is drawn black at the same opacity as the lines. Rendering uses "
                "exact physical pixels; see docs for the geometry rules.",
                "faintLabel", wrap=True,
            )
        )
        layout.addWidget(preview_card, 1)

        self.color_edit.textChanged.connect(self._on_changed)
        for spin in (self.size_spin, self.thickness_spin, self.gap_spin,
                     self.outline_thickness_spin, self.opacity_spin):
            spin.valueChanged.connect(self._on_changed)
        self.outline_check.toggled.connect(self._on_changed)

        self.reset_to_baseline()

    # ---------------------------------------------------------------- widgets
    @staticmethod
    def _int_spin(bounds: tuple[float, float]) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(int(bounds[0]), int(bounds[1]))
        return spin

    @staticmethod
    def _with_range(widget: QWidget, bounds: tuple[float, float]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(widget, 1)
        row.addWidget(label(f"{bounds[0]:g} – {bounds[1]:g}", "faintLabel"))
        return row

    # ------------------------------------------------------------------ state
    def set_config(self, config: CrosshairConfig) -> None:
        self._updating = True
        try:
            self.color_edit.setText(config.color)
            self.size_spin.setValue(round(config.size))
            self.thickness_spin.setValue(round(config.thickness))
            self.gap_spin.setValue(round(config.gap))
            self.outline_check.setChecked(config.outline_enabled)
            self.outline_thickness_spin.setValue(round(config.outline_thickness))
            self.opacity_spin.setValue(config.opacity)
        finally:
            self._updating = False
        self._on_changed()

    def current_values(self) -> dict[str, object]:
        return {
            "color": normalize_hex_color(self.color_edit.text()) or self.color_edit.text(),
            "size": float(self.size_spin.value()),
            "thickness": float(self.thickness_spin.value()),
            "gap": float(self.gap_spin.value()),
            "outline_enabled": self.outline_check.isChecked(),
            "outline_thickness": float(self.outline_thickness_spin.value()),
            "opacity": float(self.opacity_spin.value()),
        }

    def current_config(self) -> CrosshairConfig | None:
        """The edited config, or None if it is currently invalid."""
        values = self.current_values()
        if normalize_hex_color(values["color"]) is None:
            return None
        config = CrosshairConfig(**values)  # type: ignore[arg-type]
        return None if config.errors(self.context.research.parameter_ranges) else config

    def reset_to_baseline(self) -> None:
        self.set_config(CrosshairConfig.from_record(self.context.baseline_crosshair))

    def refresh_choices(self) -> None:
        self.load_combo.clear()
        for record in self.context.repository.list_crosshairs():
            fidelity = f", {display(record.fidelity)}" if record.fidelity else ""
            self.load_combo.addItem(f"{record.name} [{display(record.role)}{fidelity}]", record.crosshair_id)

    def _load_selected(self) -> None:
        crosshair_id = self.load_combo.currentData()
        record = self.context.repository.get_crosshair(crosshair_id) if crosshair_id else None
        if record is not None:
            self.set_config(CrosshairConfig.from_record(record))

    def _on_changed(self) -> None:
        if self._updating:
            return
        self.outline_thickness_spin.setEnabled(self.outline_check.isChecked())
        color = normalize_hex_color(self.color_edit.text())
        self.color_swatch.setStyleSheet(f"background-color: {color};" if color else "")
        self.color_edit.setProperty("invalid", color is None)
        self.color_edit.style().unpolish(self.color_edit)
        self.color_edit.style().polish(self.color_edit)

        config = self.current_config()
        if config is None:
            values = self.current_values()
            problems = (
                ["color must be a hex colour like #RRGGBB."]
                if normalize_hex_color(values["color"]) is None
                else CrosshairConfig(**values).errors(self.context.research.parameter_ranges)  # type: ignore[arg-type]
            )
            self.banner.show_message(" ".join(tr_message(p) for p in problems), Banner.Kind.ERROR)
            self.save_button.setEnabled(False)
            self.preview.set_shape(None)
            return
        self.banner.clear_message()
        self.save_button.setEnabled(True)
        self.preview.set_shape(config.to_shape())

    def _pick_color(self) -> None:
        current = QColor(normalize_hex_color(self.color_edit.text()) or "#FFFFFF")
        chosen = QColorDialog.getColor(current, self, tr("Crosshair colour"))
        if chosen.isValid():
            self.color_edit.setText(chosen.name().upper())

    def _save(self) -> None:
        config = self.current_config()
        name = self.name_edit.text().strip()
        if config is None:
            return
        if not name:
            self.banner.show_message("Enter a name before saving.", Banner.Kind.WARNING)
            self.name_edit.setFocus()
            return
        try:
            record = self.context.repository.add_crosshair(
                config.to_record(name, CrosshairRole.CUSTOM)
            )
        except Exception as exc:  # noqa: BLE001 - surface storage failures
            log.exception("custom_crosshair_save_failed")
            self.banner.show_message("Could not save: {error}", Banner.Kind.ERROR, error=exc)
            return
        self.banner.show_message("Saved custom crosshair '{name}'.", Banner.Kind.SUCCESS, name=name)
        self.name_edit.clear()
        self.refresh_choices()
        self.context.signals.data_changed.emit()
        self.saved.emit(record.crosshair_id)
