"""Home screen: research title, workflow overview and entry points."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.app_context import AppContext
from app.config.settings import APP_TITLE_EN, APP_TITLE_JA
from app.ui.components import BasePage, Card, MetricTile, PageId, label, primary_button, secondary_button

WORKFLOW_STEPS = [
    ("1", "Measure", "Aim assessment with the standard crosshair"),
    ("2", "Analyze", "Build a profile of measured aiming characteristics"),
    ("3", "Recommend", "Present several crosshair candidates"),
    ("4", "Try", "Apply a candidate of your choice"),
    ("5", "Re-measure", "Repeat the relevant assessment"),
    ("6", "Compare", "Review the measured differences"),
]


class HomePage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__("Home", parent=parent)
        self.context = context

        hero = Card()
        hero.body.addWidget(label(APP_TITLE_JA, "heroTitle", wrap=True))
        hero.body.addWidget(label(APP_TITLE_EN, "heroSubtitle", wrap=True))
        hero.body.addSpacing(6)
        hero.body.addWidget(
            label(
                "This research prototype measures your aiming performance, analyzes your "
                "measured characteristics, and presents crosshair candidates that may be "
                "suitable for further testing. It does not claim that any crosshair is "
                "universally best; it helps you find settings worth trying, then compares "
                "measured results.",
                "mutedLabel",
                wrap=True,
            )
        )
        hero.body.addSpacing(6)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.start_button = primary_button("Start Assessment")
        self.start_button.setToolTip("Begin with player setup (Ctrl+2)")
        self.start_button.clicked.connect(lambda: self.navigate_requested.emit(PageId.SETUP))
        crosshair_button = secondary_button("Crosshair Database")
        crosshair_button.clicked.connect(
            lambda: self.navigate_requested.emit(f"{PageId.CROSSHAIR}:database")
        )
        history_button = secondary_button("Previous Results")
        history_button.clicked.connect(lambda: self.navigate_requested.emit(PageId.HISTORY))
        settings_button = secondary_button("Settings")
        settings_button.clicked.connect(lambda: self.navigate_requested.emit(PageId.SETTINGS))
        for button in (self.start_button, crosshair_button, history_button, settings_button):
            actions.addWidget(button)
        actions.addStretch(1)
        hero.body.addLayout(actions)
        self.content.addWidget(hero)

        workflow = Card("Research workflow")
        grid = QGridLayout()
        grid.setSpacing(10)
        for index, (number, name, description) in enumerate(WORKFLOW_STEPS):
            grid.addWidget(self._workflow_step(number, name, description), 0, index)
        workflow.body.addLayout(grid)
        self.content.addWidget(workflow)

        stats_card = Card("Database")
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.tiles: dict[str, MetricTile] = {}
        for key, caption in (
            ("players", "Players"),
            ("sessions", "Sessions"),
            ("trials", "Trials"),
            ("crosshairs", "Crosshairs"),
            ("recommendations", "Recommendations"),
        ):
            tile = MetricTile(caption)
            self.tiles[key] = tile
            stats_row.addWidget(tile)
        stats_card.body.addLayout(stats_row)
        self.content.addWidget(stats_card)

        self.finish_layout()

    @staticmethod
    def _workflow_step(number: str, name: str, description: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("workflowStep")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(label(number, "badge"), 0, Qt.AlignmentFlag.AlignLeft)
        title = QLabel(name)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(label(description, "faintLabel", wrap=True))
        layout.addStretch(1)
        return frame

    def on_page_shown(self) -> None:
        self.refresh_stats()

    def refresh_stats(self) -> None:
        for key, value in self.context.repository.counts().items():
            if key in self.tiles:
                self.tiles[key].set_value(str(value))
