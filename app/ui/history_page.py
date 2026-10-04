"""Experiment history: recorded sessions and recommendation runs."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from app.app_context import AppContext
from app.i18n import display, tr
from app.ui.components import BasePage, Card, PageId, label

COLUMNS = ["Session", "Player", "Started (UTC)", "Task", "Condition", "Task order", "Position",
           "Phase", "Session #", "Status", "Crosshair", "Trials"]
RECOMMENDATION_COLUMNS = ["Run", "Player", "Created (UTC)", "Method", "Based on sessions", "Candidates (rank: name)",
                          "Selected to try"]


def _table(columns: list[str], minimum_height: int) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels([tr(c) for c in columns])
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.setMinimumHeight(minimum_height)
    return table


class HistoryPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "History",
            "All recorded sessions. Aborted sessions are kept; raw trial data is never deleted. "
            "Double-click a session to open it (candidate sessions open the comparison).",
            parent,
        )
        self.context = context
        self._comparison_sessions: set[int] = set()

        card = Card("Sessions")
        self.empty_label = label(
            "No sessions recorded yet. Sessions will appear here after an assessment is run.",
            "mutedLabel",
            wrap=True,
        )
        card.body.addWidget(self.empty_label)
        self.table = _table(COLUMNS, 320)
        self.table.cellDoubleClicked.connect(self._open_session)
        card.body.addWidget(self.table)
        self.content.addWidget(card)

        recommendations = Card("Recommendation history")
        self.rec_empty_label = label("No recommendation runs yet.", "mutedLabel")
        recommendations.body.addWidget(self.rec_empty_label)
        self.rec_table = _table(RECOMMENDATION_COLUMNS, 180)
        self.rec_table.cellDoubleClicked.connect(
            lambda *_: self.navigate_requested.emit(str(PageId.RECOMMENDATION)))
        recommendations.body.addWidget(self.rec_table)
        self.content.addWidget(recommendations)
        self.finish_layout()

    def on_page_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        summaries = self.context.repository.list_session_summaries()
        self._comparison_sessions = {
            s.session_id for s in summaries
            if str(s.condition) == "candidate" and str(s.assessment_stage) not in ("practice", "familiarization")
        }
        self.table.setRowCount(len(summaries))
        for row, s in enumerate(summaries):
            condition = display(s.condition)
            if s.condition_position:
                condition += f" ({s.condition_position}/2)"
            values = [s.session_id, s.player_id, s.started_at[:19].replace("T", " "),
                      display(s.experiment_type), condition, s.task_order_group or "–",
                      f"{s.task_position}/3" if s.task_position else "–",
                      display(s.assessment_stage) if s.assessment_stage else "–",
                      s.session_number, display(s.status),
                      s.crosshair_name, s.trial_count]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.empty_label.setVisible(not summaries)
        self.table.setVisible(bool(summaries))

        runs = self.context.repository.list_recommendations()
        self.rec_table.setRowCount(len(runs))
        for row, run in enumerate(runs):
            names = []
            selected = []
            for candidate in run["candidates"]:
                record = self.context.repository.get_crosshair(candidate["crosshair_id"])
                name = record.name if record else f"#{candidate['crosshair_id']}"
                names.append(f"{candidate['rank']}: {name}")
                if candidate["selected_by_player"]:
                    selected.append(name)
            values = [run["recommendation_id"], run["player_id"], run["created_at"][:19].replace("T", " "),
                      f"{run['method']} ({run['method_version']})",
                      ", ".join(f"#{i}" for i in run["source_session_ids"]) or "–",
                      "; ".join(names) or "–", ", ".join(selected) or "–"]
            for column, value in enumerate(values):
                self.rec_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.rec_empty_label.setVisible(not runs)
        self.rec_table.setVisible(bool(runs))

    def _open_session(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        session_id = int(item.text())
        page = PageId.COMPARISON if session_id in self._comparison_sessions else PageId.RESULTS
        self.navigate_requested.emit(f"{page}:{session_id}")
