"""Matplotlib canvas embedded in Qt, styled for the dark theme."""

from __future__ import annotations

import matplotlib
from matplotlib import font_manager
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.ui.theme import COLORS

HIT_COLOR = "#5B9BD5"
MISS_COLOR = "#E8A33D"
TIMEOUT_COLOR = "#E8524A"
BASELINE_COLOR = "#8A939C"
CANDIDATE_COLOR = "#5B9BD5"


# Japanese-capable fonts first (only those installed), so translated axis labels render.
_JAPANESE_FONTS = ("Yu Gothic", "Meiryo", "MS Gothic", "Noto Sans CJK JP", "Noto Sans JP",
                   "IPAexGothic", "Hiragino Sans")


def _configure_fonts() -> None:
    installed = {font.name for font in font_manager.fontManager.ttflist}
    available = [name for name in _JAPANESE_FONTS if name in installed]
    if available:
        current = list(matplotlib.rcParams.get("font.sans-serif", []))
        matplotlib.rcParams["font.sans-serif"] = available + [f for f in current if f not in available]
        matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["axes.unicode_minus"] = False


_configure_fonts()


class ChartCanvas(FigureCanvasQTAgg):
    def __init__(self, height_px: int = 260, parent: QWidget | None = None) -> None:
        self.figure = Figure(figsize=(6, height_px / 100), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.setMinimumHeight(height_px)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.figure.patch.set_facecolor(COLORS.surface)

    def new_axes(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(COLORS.surface)
        for spine in ax.spines.values():
            spine.set_color(COLORS.border)
        ax.tick_params(colors=COLORS.text_muted, labelsize=8)
        ax.xaxis.label.set_color(COLORS.text_muted)
        ax.yaxis.label.set_color(COLORS.text_muted)
        ax.title.set_color(COLORS.text)
        ax.grid(True, color=COLORS.border, linewidth=0.5, alpha=0.6)
        return ax

    def finish(self, ax, legend: bool = True) -> None:
        if legend and ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8, facecolor=COLORS.surface, edgecolor=COLORS.border, labelcolor=COLORS.text)
        self.figure.tight_layout()
        self.draw_idle()
