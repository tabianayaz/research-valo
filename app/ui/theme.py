"""Dark research-tool theme (Qt stylesheet + palette)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Colors:
    background: str = "#121417"
    surface: str = "#1A1D21"
    surface_alt: str = "#22262B"
    border: str = "#2E3338"
    border_strong: str = "#3D434A"
    text: str = "#E6E8EB"
    text_muted: str = "#9AA1A9"
    text_faint: str = "#6B727A"
    accent: str = "#5B9BD5"
    accent_hover: str = "#74ADE0"
    accent_pressed: str = "#4A86BD"
    success: str = "#5FB98A"
    warning: str = "#D9A84E"
    error: str = "#E06C6C"


COLORS = Colors()

FONT_FAMILIES = ["Segoe UI", "Yu Gothic UI", "Meiryo UI", "Inter", "Helvetica Neue", "Arial"]


def build_stylesheet(c: Colors = COLORS) -> str:
    return f"""
    QWidget {{
        background-color: {c.background};
        color: {c.text};
        font-size: 10pt;
    }}
    QToolTip {{
        background-color: {c.surface_alt};
        color: {c.text};
        border: 1px solid {c.border_strong};
        padding: 4px 6px;
    }}

    /* ---------- sidebar ---------- */
    #sidebar {{
        background-color: {c.surface};
        border-right: 1px solid {c.border};
    }}
    #sidebar QLabel {{ background: transparent; }}
    #sidebarTitle {{ font-size: 11pt; font-weight: 600; color: {c.text}; }}
    #sidebarSubtitle {{ font-size: 8.5pt; color: {c.text_faint}; }}
    QPushButton#navButton {{
        text-align: left;
        padding: 9px 14px;
        border: none;
        border-radius: 6px;
        background: transparent;
        color: {c.text_muted};
        font-size: 10pt;
    }}
    QPushButton#navButton:hover {{ background-color: {c.surface_alt}; color: {c.text}; }}
    QPushButton#navButton:checked {{
        background-color: {c.surface_alt};
        color: {c.text};
        border-left: 3px solid {c.accent};
        padding-left: 11px;
    }}
    QPushButton#navButton:focus {{ outline: none; border: 1px solid {c.accent}; }}

    /* ---------- typography ---------- */
    QLabel {{ background: transparent; }}
    #pageTitle {{ font-size: 18pt; font-weight: 600; }}
    #pageSubtitle {{ font-size: 10pt; color: {c.text_muted}; }}
    #sectionTitle {{ font-size: 11.5pt; font-weight: 600; }}
    #heroTitle {{ font-size: 16pt; font-weight: 600; }}
    #heroSubtitle {{ font-size: 10.5pt; color: {c.text_muted}; }}
    #mutedLabel {{ color: {c.text_muted}; }}
    #faintLabel {{ color: {c.text_faint}; font-size: 9pt; }}
    #successLabel {{ color: {c.success}; font-weight: 600; }}
    #metricValue {{ font-size: 16pt; font-weight: 600; }}
    #metricLabel {{ color: {c.text_muted}; font-size: 9pt; }}
    #badge {{
        color: {c.text_muted};
        border: 1px solid {c.border_strong};
        border-radius: 9px;
        padding: 1px 8px;
        font-size: 8.5pt;
    }}

    /* ---------- cards ---------- */
    QFrame#card {{
        background-color: {c.surface};
        border: 1px solid {c.border};
        border-radius: 8px;
    }}
    QFrame#card QLabel, QFrame#card QCheckBox {{ background: transparent; }}
    QFrame#workflowStep {{
        background-color: {c.surface_alt};
        border: 1px solid {c.border};
        border-radius: 6px;
    }}

    /* ---------- banners ---------- */
    QLabel#banner {{
        border-radius: 6px;
        padding: 8px 12px;
        border: 1px solid {c.border_strong};
        background-color: {c.surface_alt};
    }}
    QLabel#banner[kind="success"] {{ border-color: {c.success}; color: {c.success}; }}
    QLabel#banner[kind="error"]   {{ border-color: {c.error};   color: {c.error}; }}
    QLabel#banner[kind="warning"] {{ border-color: {c.warning}; color: {c.warning}; }}
    QLabel#banner[kind="info"]    {{ border-color: {c.accent};  color: {c.text}; }}

    /* ---------- buttons ---------- */
    QPushButton {{
        background-color: {c.surface_alt};
        border: 1px solid {c.border_strong};
        border-radius: 6px;
        padding: 7px 16px;
        color: {c.text};
    }}
    QPushButton:hover {{ border-color: {c.text_faint}; }}
    QPushButton:pressed {{ background-color: {c.border}; }}
    QPushButton:focus {{ border: 1px solid {c.accent}; }}
    QPushButton:disabled {{ color: {c.text_faint}; border-color: {c.border}; background-color: {c.surface}; }}
    QPushButton#primaryButton {{
        background-color: {c.accent};
        border: 1px solid {c.accent};
        color: #0E1114;
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{ background-color: {c.accent_hover}; }}
    QPushButton#primaryButton:pressed {{ background-color: {c.accent_pressed}; }}
    QPushButton#primaryButton:focus {{ border: 2px solid {c.text}; }}
    QPushButton#primaryButton:disabled {{
        background-color: {c.surface_alt}; border-color: {c.border}; color: {c.text_faint};
    }}

    /* ---------- inputs ---------- */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
        background-color: {c.surface_alt};
        border: 1px solid {c.border_strong};
        border-radius: 5px;
        padding: 5px 8px;
        selection-background-color: {c.accent};
        selection-color: #0E1114;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {c.accent};
    }}
    QLineEdit:read-only, QDoubleSpinBox:read-only {{ color: {c.text_muted}; background-color: {c.surface}; }}
    QLineEdit[invalid="true"] {{ border: 1px solid {c.error}; }}
    QComboBox QAbstractItemView {{
        background-color: {c.surface_alt};
        border: 1px solid {c.border_strong};
        selection-background-color: {c.accent};
        selection-color: #0E1114;
    }}

    /* ---------- tabs ---------- */
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{
        background: transparent;
        color: {c.text_muted};
        padding: 8px 16px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{ color: {c.text}; }}
    QTabBar::tab:selected {{ color: {c.text}; border-bottom: 2px solid {c.accent}; }}
    QTabBar::tab:focus {{ outline: none; background-color: {c.surface_alt}; }}

    /* ---------- checkboxes ---------- */
    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {c.border_strong};
        border-radius: 3px;
        background-color: {c.surface_alt};
    }}
    QCheckBox::indicator:checked {{ background-color: {c.accent}; border-color: {c.accent}; }}
    QCheckBox:focus {{ color: {c.accent_hover}; }}

    QPushButton#colorSwatch {{ min-width: 28px; max-width: 28px; padding: 0; }}

    /* ---------- tables ---------- */
    QTableWidget, QTableView {{
        background-color: {c.surface};
        alternate-background-color: {c.surface_alt};
        border: 1px solid {c.border};
        border-radius: 6px;
        gridline-color: {c.border};
    }}
    QHeaderView::section {{
        background-color: {c.surface_alt};
        color: {c.text_muted};
        border: none;
        border-bottom: 1px solid {c.border};
        padding: 6px 8px;
        font-weight: 600;
    }}
    QTableWidget::item:selected {{ background-color: {c.accent}; color: #0E1114; }}

    /* ---------- scroll ---------- */
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c.border_strong}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {c.border_strong}; border-radius: 4px; min-width: 30px; }}

    QStatusBar {{
        background-color: {c.surface};
        border-top: 1px solid {c.border};
        color: {c.text_muted};
    }}
    QStatusBar QLabel {{ color: {c.text_muted}; padding: 0 8px; }}
    """


def apply_theme(app: QApplication) -> None:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(10)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS.background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS.surface_alt))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS.surface))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS.surface_alt))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0E1114"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLORS.text_faint))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet())
