"""Reusable UI building blocks shared by all pages."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import clear_tr_binding, mark_source, set_tr_text, tr


class PageId(StrEnum):
    HOME = "home"
    SETUP = "setup"
    CROSSHAIR = "crosshair"
    ASSESSMENT = "assessment"
    RESULTS = "results"
    RECOMMENDATION = "recommendation"
    COMPARISON = "comparison"
    HISTORY = "history"
    SETTINGS = "settings"


def label(text: str, object_name: str | None = None, wrap: bool = False) -> QLabel:
    widget = QLabel(tr(text))
    mark_source(widget, text)
    if object_name:
        widget.setObjectName(object_name)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def primary_button(text: str) -> QPushButton:
    button = QPushButton(tr(text))
    mark_source(button, text)
    button.setObjectName("primaryButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def secondary_button(text: str) -> QPushButton:
    button = QPushButton(tr(text))
    mark_source(button, text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class Card(QFrame):
    """Bordered surface container with an optional title."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        self.title_label: QLabel | None = None
        if title:
            self.title_label = label(title, "sectionTitle")
            self.body.addWidget(self.title_label)

    def set_title(self, title: str) -> None:
        if self.title_label is not None:
            self.title_label.setText(tr(title))
            mark_source(self.title_label, title)


class Banner(QLabel):
    """Inline status message (info / success / warning / error)."""

    class Kind(StrEnum):
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        ERROR = "error"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        self.setWordWrap(True)
        self.hide()

    def show_message(self, text: str, kind: "Banner.Kind" = Kind.INFO, **values: object) -> None:
        """Show ``text`` (an English source template) in the current language.

        The message re-translates itself when the UI language changes.
        """
        set_tr_text(self, text, **values)
        self.setProperty("kind", str(kind))
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()

    def clear_message(self) -> None:
        clear_tr_binding(self)
        self.clear()
        self.hide()


class MetricTile(QFrame):
    """Small labelled number display."""

    def __init__(self, caption: str, value: str = "–", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)
        self.value_label = label(value, "metricValue")
        layout.addWidget(self.value_label)
        layout.addWidget(label(caption, "metricLabel"))

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class BasePage(QWidget):
    """Scrollable page with a consistent header.

    Subclasses add widgets to ``self.content``. Pages request navigation by
    emitting ``navigate_requested`` rather than reaching into the main window.
    """

    navigate_requested = Signal(str)

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        self.content = QVBoxLayout(container)
        self.content.setContentsMargins(36, 28, 36, 28)
        self.content.setSpacing(16)

        self.content.addWidget(label(title, "pageTitle"))
        if subtitle:
            self.content.addWidget(label(subtitle, "pageSubtitle", wrap=True))

    def on_page_shown(self) -> None:
        """Hook called by the main window whenever this page becomes visible."""

    def show_section(self, section: str) -> None:
        """Hook for ``"<page>:<section>"`` navigation targets (e.g. a specific tab)."""

    def finish_layout(self) -> None:
        self.content.addStretch(1)


class PlaceholderPage(BasePage):
    """Page that is planned but not implemented in the current milestone."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        milestone: str,
        planned_items: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, subtitle, parent)
        card = Card("Not yet available")
        card.body.addWidget(
            label(tr("This screen will be implemented in {milestone}.", milestone=milestone), "mutedLabel", wrap=True)
        )
        if planned_items:
            card.body.addWidget(label("Planned contents:", "mutedLabel"))
            for item in planned_items:
                card.body.addWidget(label(f"•  {item}", wrap=True))
        self.content.addWidget(card)
        self.finish_layout()


def combo_box(minimum_width: int) -> QComboBox:
    """Combo box that does not grow to its longest item (avoids horizontal page scrolling)."""
    combo = QComboBox()
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(20)
    combo.setMinimumWidth(minimum_width)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return combo


def hbox(*widgets: QWidget, spacing: int = 10, stretch_end: bool = True) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch_end:
        layout.addStretch(1)
    return layout


def expanding(widget: QWidget) -> QWidget:
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return widget
