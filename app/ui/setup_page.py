"""Player setup: anonymous ID and hardware / experience information."""

from __future__ import annotations

import secrets

from PySide6.QtGui import QGuiApplication, QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from app.app_context import AppContext
from app.data.models import Player
from app.i18n import tr
from app.utils.logging import get_logger
from app.utils.validators import ValidationError, validate_player_id
from app.ui.components import Banner, BasePage, Card, PageId, label, primary_button, secondary_button

log = get_logger("ui.setup")

# Research decision pending: these categories are provisional placeholders and
# should be replaced with the questionnaire categories agreed with the supervisor.
FPS_EXPERIENCE_OPTIONS = [
    "Not specified",
    "Less than 6 months",
    "6 months - 1 year",
    "1 - 3 years",
    "More than 3 years",
]
AIM_TRAINING_OPTIONS = [
    "Not specified",
    "Never",
    "Rarely (less than once a month)",
    "Sometimes (a few times a month)",
    "Regularly (weekly)",
    "Daily",
]


class SetupPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Player Setup",
            "Anonymous participant information. Do not enter your real name, email or any "
            "other personally identifying information.",
            parent,
        )
        self.context = context

        self.banner = Banner()
        self.content.addWidget(self.banner)

        identity = Card("Participant")
        identity_form = QFormLayout()
        identity_form.setHorizontalSpacing(18)
        identity_form.setVerticalSpacing(10)

        self.player_id_edit = QLineEdit()
        self.player_id_edit.setPlaceholderText("e.g. P-3F9A")
        self.player_id_edit.setMaxLength(32)
        self.player_id_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"[A-Za-z0-9_-]{0,32}"))
        )
        self.player_id_edit.editingFinished.connect(self._load_existing_player)
        generate_button = secondary_button("Generate ID")
        generate_button.clicked.connect(self._generate_player_id)
        id_row = QHBoxLayout()
        id_row.addWidget(self.player_id_edit, 1)
        id_row.addWidget(generate_button)
        identity_form.addRow("Player ID", id_row)

        self.fps_experience_combo = QComboBox()
        self._fill_combo(self.fps_experience_combo, FPS_EXPERIENCE_OPTIONS)
        identity_form.addRow("FPS experience", self.fps_experience_combo)

        self.aim_training_combo = QComboBox()
        self._fill_combo(self.aim_training_combo, AIM_TRAINING_OPTIONS)
        identity_form.addRow("Aim training frequency", self.aim_training_combo)
        identity.body.addLayout(identity_form)
        self.content.addWidget(identity)

        hardware = Card("Mouse and display")
        hardware_form = QFormLayout()
        hardware_form.setHorizontalSpacing(18)
        hardware_form.setVerticalSpacing(10)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(100, 32000)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setValue(800)
        hardware_form.addRow("Mouse DPI", self.dpi_spin)

        self.sensitivity_spin = QDoubleSpinBox()
        self.sensitivity_spin.setDecimals(3)
        self.sensitivity_spin.setRange(0.001, 100.0)
        self.sensitivity_spin.setSingleStep(0.05)
        self.sensitivity_spin.setValue(0.5)
        hardware_form.addRow("In-game sensitivity", self.sensitivity_spin)

        self.edpi_edit = QLineEdit()
        self.edpi_edit.setReadOnly(True)
        hardware_form.addRow("eDPI (DPI × sensitivity)", self.edpi_edit)

        self.display_width_spin = QSpinBox()
        self.display_width_spin.setRange(320, 15360)
        self.display_height_spin = QSpinBox()
        self.display_height_spin.setRange(240, 8640)
        resolution_row = QHBoxLayout()
        resolution_row.addWidget(self.display_width_spin)
        resolution_row.addWidget(label("×", "mutedLabel"))
        resolution_row.addWidget(self.display_height_spin)
        detect_button = secondary_button("Detect")
        detect_button.setToolTip("Use the resolution of the screen this window is on")
        detect_button.clicked.connect(self._detect_resolution)
        resolution_row.addWidget(detect_button)
        resolution_row.addStretch(1)
        hardware_form.addRow("Display resolution", resolution_row)
        hardware.body.addLayout(hardware_form)
        hardware.body.addWidget(
            label(
                "eDPI is computed as DPI × in-game sensitivity. Sensitivity scales differ "
                "between games, so record the game the sensitivity refers to in a later "
                "milestone if cross-game comparison becomes necessary.",
                "faintLabel",
                wrap=True,
            )
        )
        self.content.addWidget(hardware)

        actions = QHBoxLayout()
        self.save_button = primary_button("Save and Continue")
        self.save_button.clicked.connect(self._save_and_continue)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        self.content.addLayout(actions)
        self.finish_layout()

        self.dpi_spin.valueChanged.connect(self._update_edpi)
        self.sensitivity_spin.valueChanged.connect(self._update_edpi)
        self._update_edpi()
        self._detect_resolution()

    # ----------------------------------------------------------------- helpers
    def _generate_player_id(self) -> None:
        existing = {p.player_id for p in self.context.repository.list_players()}
        while True:
            candidate = f"P-{secrets.token_hex(2).upper()}"
            if candidate not in existing:
                break
        self.player_id_edit.setText(candidate)
        self.banner.clear_message()

    def _update_edpi(self) -> None:
        self.edpi_edit.setText(f"{self._edpi():g}")

    def _edpi(self) -> float:
        return round(self.dpi_spin.value() * self.sensitivity_spin.value(), 3)

    def _detect_resolution(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        size = screen.size()
        ratio = screen.devicePixelRatio()
        self.display_width_spin.setValue(round(size.width() * ratio))
        self.display_height_spin.setValue(round(size.height() * ratio))

    def _load_existing_player(self) -> None:
        text = self.player_id_edit.text().strip()
        if not text:
            return
        player = self.context.repository.get_player(text)
        if player is None:
            return
        self._populate(player)
        self.banner.show_message(
            "Loaded existing participant {player_id}. Saving will update the profile; "
            "past sessions keep their own recorded settings.",
            Banner.Kind.INFO,
            player_id=player.player_id,
        )

    def _populate(self, player: Player) -> None:
        self.player_id_edit.setText(player.player_id)
        self._set_combo(self.fps_experience_combo, player.fps_experience)
        self._set_combo(self.aim_training_combo, player.aim_training_frequency)
        if player.mouse_dpi:
            self.dpi_spin.setValue(player.mouse_dpi)
        if player.sensitivity:
            self.sensitivity_spin.setValue(player.sensitivity)
        if player.display_width:
            self.display_width_spin.setValue(player.display_width)
        if player.display_height:
            self.display_height_spin.setValue(player.display_height)

    @staticmethod
    def _set_combo(combo: QComboBox, value: str | None) -> None:
        # Stored values are the English option text (item data), independent of UI language.
        index = combo.findData(value) if value else 0
        combo.setCurrentIndex(max(index, 0))

    @staticmethod
    def _fill_combo(combo: QComboBox, options: list[str]) -> None:
        for option in options:
            combo.addItem(tr(option), option)

    @staticmethod
    def _combo_value(combo: QComboBox) -> str | None:
        return None if combo.currentIndex() == 0 else combo.currentData()

    def build_player(self) -> Player:
        return Player(
            player_id=validate_player_id(self.player_id_edit.text()),
            fps_experience=self._combo_value(self.fps_experience_combo),
            aim_training_frequency=self._combo_value(self.aim_training_combo),
            mouse_dpi=self.dpi_spin.value(),
            sensitivity=self.sensitivity_spin.value(),
            edpi=self._edpi(),
            display_width=self.display_width_spin.value(),
            display_height=self.display_height_spin.value(),
        )

    def _save_and_continue(self) -> None:
        self.player_id_edit.setProperty("invalid", False)
        try:
            player = self.context.repository.save_player(self.build_player())
        except ValidationError as exc:
            self.player_id_edit.setProperty("invalid", True)
            self._repolish(self.player_id_edit)
            self.banner.show_message(str(exc), Banner.Kind.ERROR)
            self.player_id_edit.setFocus()
            return
        except Exception as exc:  # noqa: BLE001 - surface any storage failure to the user
            log.exception("player_save_failed")
            self.banner.show_message("Could not save participant: {error}", Banner.Kind.ERROR, error=exc)
            return
        self._repolish(self.player_id_edit)
        self.context.set_current_player(player)
        self.context.signals.data_changed.emit()
        self.banner.show_message(
            "Participant {player_id} saved.", Banner.Kind.SUCCESS, player_id=player.player_id
        )
        self.navigate_requested.emit(PageId.CROSSHAIR)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def on_page_shown(self) -> None:
        if self.context.current_player and not self.player_id_edit.text():
            self._populate(self.context.current_player)
