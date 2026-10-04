"""Main window: sidebar navigation + stacked pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.app_context import AppContext
from app.config.settings import APP_NAME
from app.data.models import Player
from app.i18n import WindowTranslationFilter, is_japanese, retranslate_tree, tr, translator
from app.ui.aim_selection_page import AimSelectionPage
from app.ui.comparison_page import ComparisonPage
from app.ui.components import BasePage, PageId
from app.ui.crosshair_page import CrosshairPage
from app.ui.history_page import HistoryPage
from app.ui.home_page import HomePage
from app.ui.recommendation_page import RecommendationPage
from app.ui.results_page import ResultsPage
from app.ui.settings_page import SettingsPage
from app.ui.setup_page import SetupPage
from app.utils.logging import get_logger

log = get_logger("ui.main_window")

NAV_ITEMS: list[tuple[PageId, str]] = [
    (PageId.HOME, "Home"),
    (PageId.SETUP, "Setup"),
    (PageId.CROSSHAIR, "Crosshair"),
    (PageId.ASSESSMENT, "Assessment"),
    (PageId.RESULTS, "Results"),
    (PageId.RECOMMENDATION, "Recommendation"),
    (PageId.COMPARISON, "Comparison"),
    (PageId.HISTORY, "History"),
    (PageId.SETTINGS, "Settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 720)

        self.pages: dict[PageId, BasePage] = {
            PageId.HOME: HomePage(context),
            PageId.SETUP: SetupPage(context),
            PageId.CROSSHAIR: CrosshairPage(context),
            PageId.ASSESSMENT: AimSelectionPage(context),
            PageId.RESULTS: ResultsPage(context),
            PageId.RECOMMENDATION: RecommendationPage(context),
            PageId.COMPARISON: ComparisonPage(context),
            PageId.HISTORY: HistoryPage(context),
            PageId.SETTINGS: SettingsPage(context),
        }

        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)
            page.navigate_requested.connect(self.navigate)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self._build_status_bar()
        self._install_shortcuts()
        context.signals.player_changed.connect(self._on_player_changed)
        context.signals.data_changed.connect(self._schedule_retranslate)

        self._window_filter = WindowTranslationFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._window_filter)
        translator.language_changed.connect(self._on_language_changed)
        self._retranslate_pending = False

        self.navigate(PageId.HOME)
        QTimer.singleShot(0, self.pages[PageId.HOME].start_button.setFocus)

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(4)

        title = QLabel(APP_NAME)
        title.setObjectName("sidebarTitle")
        subtitle = QLabel(tr("HCI research prototype"))
        subtitle.setObjectName("sidebarSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[PageId, QPushButton] = {}
        for page_id, text in NAV_ITEMS:
            button = QPushButton(tr(text))
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.clicked.connect(lambda _checked=False, pid=page_id: self.navigate(pid))
            self.nav_group.addButton(button)
            self.nav_buttons[page_id] = button
            layout.addWidget(button)
        self._update_nav_tooltips()

        layout.addStretch(1)
        self.language_button = QPushButton()
        self.language_button.setObjectName("languageButton")
        self.language_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_button.clicked.connect(self.toggle_language)
        self._update_language_button()
        layout.addWidget(self.language_button)
        layout.addSpacing(6)
        version = QLabel(f"v{__version__}")
        version.setObjectName("sidebarSubtitle")
        layout.addWidget(version)
        return sidebar

    def _build_status_bar(self) -> None:
        self.player_status = QLabel()
        self.db_status = QLabel()
        self.db_status.setToolTip(str(self.context.settings.db_path))
        self._update_db_status()
        self.statusBar().addWidget(self.player_status)
        self.statusBar().addPermanentWidget(self.db_status)
        self._on_player_changed(self.context.current_player)

    def _install_shortcuts(self) -> None:
        for index, (page_id, _text) in enumerate(NAV_ITEMS, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda pid=page_id: self.navigate(pid))

    # -------------------------------------------------------------- navigation
    def navigate(self, target: str) -> None:
        """Show a page. ``target`` is a PageId or ``"<page_id>:<section>"``."""
        page_part, _, section = str(target).partition(":")
        pid = PageId(page_part)
        page = self.pages[pid]
        self.stack.setCurrentWidget(page)
        self.nav_buttons[pid].setChecked(True)
        page.on_page_shown()
        if section:
            page.show_section(section)
        if is_japanese():
            retranslate_tree(page)
        log.info("navigate page=%s section=%s", pid, section or "-")

    def current_page_id(self) -> PageId:
        current = self.stack.currentWidget()
        return next(pid for pid, page in self.pages.items() if page is current)

    def _on_player_changed(self, player: Player | None) -> None:
        self._current_player = player
        text = (
            tr("Participant: {player_id}", player_id=player.player_id)
            if player
            else tr("No participant selected")
        )
        self.player_status.setText(text)

    # ---------------------------------------------------------------- language
    def toggle_language(self) -> None:
        translator.toggle()

    def _update_language_button(self) -> None:
        # The button names the language it switches *to*.
        if is_japanese():
            self.language_button.setText("English")
            self.language_button.setToolTip("Switch the interface to English")
        else:
            self.language_button.setText("日本語")
            self.language_button.setToolTip("表示言語を日本語に切り替えます")

    def _update_nav_tooltips(self) -> None:
        for index, (page_id, text) in enumerate(NAV_ITEMS, start=1):
            button = self.nav_buttons[page_id]
            button.setText(tr(text))
            button.setToolTip(f"{tr(text)} (Ctrl+{index})")

    def _update_db_status(self) -> None:
        self.db_status.setText(
            tr("Database: {name}", name=self.context.settings.db_path.name)
        )

    def _on_language_changed(self, language: str) -> None:
        log.info("language_changed language=%s", language)
        self._update_language_button()
        self._update_nav_tooltips()
        self._update_db_status()
        self._on_player_changed(self.context.current_player)
        # Static texts on every page, then rebuild dynamic text on the visible page.
        retranslate_tree(self)
        current = self.stack.currentWidget()
        if isinstance(current, BasePage):
            current.on_page_shown()
            retranslate_tree(current)
        for widget in QApplication.topLevelWidgets():
            if widget is not self and widget.isVisible():
                retranslate_tree(widget)
                widget.update()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # The translator is process-wide; a closed window must stop reacting to it.
        try:
            translator.language_changed.disconnect(self._on_language_changed)
        except (RuntimeError, TypeError):
            pass
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._window_filter)
        super().closeEvent(event)

    def _schedule_retranslate(self) -> None:
        if not is_japanese() or self._retranslate_pending:
            return
        self._retranslate_pending = True

        def run() -> None:
            self._retranslate_pending = False
            if is_japanese():
                retranslate_tree(self)

        QTimer.singleShot(0, run)
