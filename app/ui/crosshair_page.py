"""Crosshair screen: standard (baseline) crosshair, settings editor, candidate database."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QTabWidget, QVBoxLayout, QWidget

from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.i18n import set_tr_text, tr
from app.ui.components import Banner, BasePage, Card, label
from app.ui.crosshair_database import CrosshairDatabaseView
from app.ui.crosshair_editor import CrosshairEditor
from app.ui.crosshair_widgets import ParameterList, PreviewPanel

TAB_STANDARD = "standard"
TAB_EDITOR = "editor"
TAB_DATABASE = "database"


class StandardCrosshairView(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.banner = Banner()
        layout.addWidget(self.banner)
        if not context.research.baseline_confirmed:
            self.banner.show_message(
                "Research decision required: the standard crosshair values are placeholders "
                "and have not been confirmed. Set them and \"baseline_confirmed\": true in "
                "{file} before collecting data.",
                Banner.Kind.WARNING,
                file=context.research.source_path.name,
            )

        row = QHBoxLayout()
        row.setSpacing(16)
        values_card = Card("Experimental baseline")
        values_card.body.addWidget(label(
            "Every participant performs the initial assessment with this fixed crosshair. "
            "Holding it constant makes first measurements comparable between participants "
            "and gives each participant a reference for later candidate comparisons.",
            "mutedLabel", wrap=True,
        ))
        self.parameters = ParameterList()
        values_card.body.addWidget(self.parameters)
        self.meta = label("", "faintLabel", wrap=True)
        values_card.body.addWidget(self.meta)
        values_card.body.addStretch(1)
        values_card.setMinimumWidth(340)
        row.addWidget(values_card, 0)

        preview_card = Card("Preview")
        self.preview = PreviewPanel(context.research)
        preview_card.body.addWidget(self.preview, 1)
        row.addWidget(preview_card, 1)
        layout.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        record = self.context.baseline_crosshair
        config = CrosshairConfig.from_record(record)
        self.parameters.set_config(config)
        self.preview.set_shape(config.to_shape())
        set_tr_text(
            self.meta,
            "Crosshair ID {crosshair_id} · defined in {path} · background {background}",
            crosshair_id=record.crosshair_id,
            path=str(self.context.research.source_path),
            background=self.context.research.experiment_background_color,
        )


class CrosshairPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Crosshair",
            "Standard crosshair, crosshair settings and the candidate crosshair database.",
            parent,
        )
        self.context = context
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.standard = StandardCrosshairView(context)
        self.editor = CrosshairEditor(context)
        self.database = CrosshairDatabaseView(context)
        self.tabs.addTab(self.standard, "Standard crosshair")
        self.tabs.addTab(self.editor, "Crosshair settings")
        self.tabs.addTab(self.database, "Crosshair database")
        self._tab_index = {TAB_STANDARD: 0, TAB_EDITOR: 1, TAB_DATABASE: 2}
        self.tabs.currentChanged.connect(lambda _i: self._refresh_current())
        self.database.crosshair_selected.connect(self._open_in_editor)
        self.content.addWidget(self.tabs, 1)

    def on_page_shown(self) -> None:
        self.standard.refresh()
        self._refresh_current()

    def show_section(self, section: str) -> None:
        if section in self._tab_index:
            self.tabs.setCurrentIndex(self._tab_index[section])

    def _refresh_current(self) -> None:
        current = self.tabs.currentWidget()
        if current is self.database:
            self.database.refresh()
        elif current is self.editor:
            self.editor.refresh_choices()

    def _open_in_editor(self, crosshair_id: int) -> None:
        record = self.context.repository.get_crosshair(crosshair_id)
        if record is None:
            return
        self.tabs.setCurrentIndex(self._tab_index[TAB_EDITOR])
        self.editor.set_config(CrosshairConfig.from_record(record))
