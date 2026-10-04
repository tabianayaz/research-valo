"""Results screen: metrics, trial table and charts for one session (Milestone 4).

All values are recomputed from raw trial data when a session is opened
(``app.analysis.metrics``) and stored in ``aim_results`` as derived data.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.analysis.export import export_session
from app.analysis.metrics import ANALYSIS_VERSION, SessionAnalysis, analyze_session, format_metric
from app.app_context import AppContext
from app.data.models import ExperimentType, TrialResult, TrialStatus
from app.experiment.timing import ONSET_FALLBACK_MS
from app.experiment.task_order import format_task_order
from app.i18n import display, set_tr_text, tr, tr_message
from app.ui.charts import HIT_COLOR, MISS_COLOR, TIMEOUT_COLOR, ChartCanvas
from app.ui.components import BasePage, Banner, Card, MetricTile, combo_box, label, secondary_button
from app.ui.session_format import session_label
from app.utils.logging import get_logger

log = get_logger("ui.results")

POINTING_COLUMNS = ["#", "Target", "Result", "Reaction (ms)", "Completion (ms)", "Click error (px)",
                    "Target distance (px)", "Moved at onset", "Validity"]
TRACKING_COLUMNS = ["#", "Trial", "Result", "Reaction (ms)", "Time on target", "Mean distance (px)",
                    "RMS distance (px)", "Moved at onset", "Validity"]


def _fmt(value: float | None, digits: int = 0) -> str:
    return "–" if value is None else f"{value:.{digits}f}"


class ResultsPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Results",
            "Measured results of one session, recomputed from the raw trial data. "
            "Values describe this session only; they are not norms or ratings.",
            parent,
        )
        self.context = context
        self.analysis: SessionAnalysis | None = None
        self._pending_session_id: int | None = None

        picker_row = QHBoxLayout()
        self.session_combo = combo_box(420)
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)
        self.export_button = secondary_button("Export CSV / JSON")
        self.export_button.clicked.connect(self._export)
        picker_row.addWidget(label("Session", "mutedLabel"))
        picker_row.addWidget(self.session_combo, 1)
        picker_row.addWidget(self.export_button)
        self.content.addLayout(picker_row)

        self.banner = Banner()
        self.content.addWidget(self.banner)
        self.notes_banner = Banner()
        self.content.addWidget(self.notes_banner)

        self.metrics_card = Card("Session metrics")
        self.metrics_grid = QGridLayout()
        self.metrics_grid.setSpacing(10)
        self.metrics_card.body.addLayout(self.metrics_grid)
        self.analysis_note = label("", "faintLabel", wrap=True)
        set_tr_text(
            self.analysis_note,
            "Analysis version {version}. Medians for times; completion and switching times "
            "use hit trials only; click error uses hits and misses.",
            version=ANALYSIS_VERSION,
        )
        self.metrics_card.body.addWidget(self.analysis_note)
        self.content.addWidget(self.metrics_card)

        self.chart_card = Card("Per-trial chart")
        self.chart = ChartCanvas(260)
        self.chart_card.body.addWidget(self.chart)
        self.content.addWidget(self.chart_card)

        self.table_card = Card("Trials")
        self.table = QTableWidget(0, len(POINTING_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(300)
        self.table_card.body.addWidget(self.table)
        self.content.addWidget(self.table_card)
        self.finish_layout()

    # ------------------------------------------------------------- navigation
    def on_page_shown(self) -> None:
        self.reload_sessions()

    def show_section(self, section: str) -> None:
        if section.isdigit():
            self.select_session(int(section))

    def select_session(self, session_id: int) -> None:
        index = self.session_combo.findData(session_id)
        if index >= 0:
            self.session_combo.setCurrentIndex(index)
            if self.analysis is None or self.analysis.session.session_id != session_id:
                self._on_session_changed(index)

    def reload_sessions(self) -> None:
        current = self.session_combo.currentData()
        player = self.context.current_player
        sessions = self.context.repository.list_sessions(player.player_id if player else None)
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        for session in sessions:
            crosshair = self.context.repository.get_crosshair(session.crosshair_id)
            self.session_combo.addItem(session_label(session, crosshair.name if crosshair else None),
                                       session.session_id)
        self.session_combo.blockSignals(False)
        has_sessions = bool(sessions)
        for widget in (self.metrics_card, self.chart_card, self.table_card, self.export_button):
            widget.setVisible(has_sessions)
        if not has_sessions:
            if player:
                self.banner.show_message(
                    "No sessions recorded for participant {player_id} yet. Run an assessment first.",
                    Banner.Kind.INFO, player_id=player.player_id)
            else:
                self.banner.show_message("No sessions recorded yet. Run an assessment first.",
                                         Banner.Kind.INFO)
            self.notes_banner.clear_message()
            self.analysis = None
            return
        index = self.session_combo.findData(current)
        self.session_combo.setCurrentIndex(index if index >= 0 else 0)
        self._on_session_changed(self.session_combo.currentIndex())

    # --------------------------------------------------------------- display
    def _on_session_changed(self, index: int) -> None:
        session_id = self.session_combo.itemData(index)
        if session_id is None:
            return
        try:
            self.analysis = analyze_session(self.context.repository, session_id)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            log.exception("analysis_failed session_id=%s", session_id)
            self.banner.show_message("Could not analyse session {session_id}: {error}", Banner.Kind.ERROR,
                                     session_id=session_id, error=exc)
            return
        self._show_banners()
        self._show_metrics()
        self._show_chart()
        self._show_table()

    def _show_banners(self) -> None:
        a = self.analysis
        messages = []
        if str(a.session.status) != "completed":
            messages.append(tr("Session status: {status}. Metrics use the trials that were saved.",
                               status=display(a.session.status)))
        if a.mismatches:
            messages.append(tr("{count} recomputed values differ from the values stored during "
                               "recording (first: {first}).", count=len(a.mismatches), first=a.mismatches[0]))
        if a.excluded_rows:
            messages.append(tr("{count} rows from restarted switching trials are excluded "
                               "(latest attempt used).", count=a.excluded_rows))
        invalid = int(a.metrics.get("invalid_pre_movement_count") or 0)
        if invalid:
            messages.append(tr("{count} trials were invalidated because the mouse moved before the target "
                               "appeared; they were repeated and are excluded from all metrics.", count=invalid))
        fallback = int(a.metrics.get("timing_fallback_count") or 0)
        if fallback:
            messages.append(tr("{count} trials used the {ms} ms timing fallback (target onset "
                               "not confirmed by a paint); they are excluded from time measures.",
                               count=fallback, ms=ONSET_FALLBACK_MS))
        if messages:
            self.banner.show_message(" ".join(messages), Banner.Kind.WARNING)
        else:
            self.banner.show_message(
                "{count} trials recomputed from raw samples and events; all match the recorded values.",
                Banner.Kind.SUCCESS, count=len(a.rows),
            )
        notes = []
        if a.session.notes:
            notes.append(tr_message(a.session.notes))  # display only; stored notes stay English
        notes.append(tr("Protocol: {protocol}.", protocol=a.session.protocol_version
                        or tr("not recorded (session before protocol versioning)")))
        if a.session.task_order:
            position = (tr(", position {position}/3", position=a.session.task_position)
                        if a.session.task_position else "")
            notes.append(tr(
                "Task order: {order} (group {group}{position}).",
                order=format_task_order(a.session.task_order, short=True),
                group=a.session.task_order_group or tr("not recorded"),
                position=position,
            ))
        else:
            notes.append(tr("Task order: not recorded (historical session)."))
        practice = int(a.metrics.get("practice_trials") or 0)
        if practice:
            notes.append(tr("{count} practice trials are listed for audit but are not analysed.", count=practice))
        moving = a.metrics.get("moving_at_onset_rate")
        if moving is not None and moving > 0.25:
            notes.append(tr("The crosshair was moving at target onset in {percent} % of trials, so "
                            "reaction time mostly reflects ongoing movement rather than a response to the target.",
                            percent=f"{moving * 100:.0f}"))
        if notes:
            self.notes_banner.show_message(" ".join(notes), Banner.Kind.INFO)
        else:
            self.notes_banner.clear_message()

    def _show_metrics(self) -> None:
        while self.metrics_grid.count():
            item = self.metrics_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (name, definition, value) in enumerate(self.analysis.metric_items()):
            tile = MetricTile(definition.label, format_metric(name, value))
            tile.setToolTip(tr(definition.description))
            self.metrics_grid.addWidget(tile, i // 4, i % 4)

    def _show_chart(self) -> None:
        a = self.analysis
        ax = self.chart.new_axes()
        task = ExperimentType(a.session.experiment_type)
        if task == ExperimentType.TRACKING:
            tracked = [r for r in a.rows if r.valid_for_tracking]
            ax.bar([r.trial.trial_number for r in tracked], [(r.on_target_ratio or 0) * 100 for r in tracked],
                   color=HIT_COLOR)
            ax.set_ylabel(tr("time on target (%)"))
            ax.set_ylim(0, 100)
            self.chart_card.set_title("Time on target per trial")
        else:
            timed = [r for r in a.rows if r.status == TrialStatus.VALID and not r.excluded]
            for result, color, marker in ((TrialResult.HIT, HIT_COLOR, "o"), (TrialResult.MISS, MISS_COLOR, "x")):
                points = [(r.trial.trial_number, r.completion_time_ms) for r in timed
                          if r.result == result and r.completion_time_ms is not None]
                if points:
                    ax.scatter(*zip(*points), color=color, marker=marker, s=28, label=display(result))
            timeouts = [r.trial.trial_number for r in a.rows if r.result == TrialResult.TIMEOUT and not r.excluded]
            if timeouts:
                top = max([r.completion_time_ms or 0 for r in a.rows] + [1])
                ax.scatter(timeouts, [top] * len(timeouts), color=TIMEOUT_COLOR, marker="^", s=28,
                           label=display("timeout"))
            ax.set_ylabel(tr("completion time (ms)"))
            self.chart_card.set_title(
                "Completion time per trial" if task == ExperimentType.FLICK
                else "Time per target (first target and switches)")
        ax.set_xlabel(tr("trial"))
        self.chart.finish(ax)

    def _show_table(self) -> None:
        a = self.analysis
        tracking = ExperimentType(a.session.experiment_type) == ExperimentType.TRACKING
        columns = TRACKING_COLUMNS if tracking else POINTING_COLUMNS
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([tr(c) for c in columns])
        self.table.setRowCount(len(a.rows))
        for row_index, r in enumerate(a.rows):
            moved = "–" if r.moving_at_onset is None else tr("yes" if r.moving_at_onset else "no")
            if tracking:
                values = [r.trial.trial_number, r.trial.target_id, display(r.result), _fmt(r.reaction_time_ms),
                          "–" if r.on_target_ratio is None else f"{r.on_target_ratio * 100:.1f} %",
                          _fmt(r.mean_distance, 1), _fmt(r.rms_distance, 1), moved, tr(r.validity_label())]
            else:
                values = [r.trial.trial_number, r.trial.target_id, display(r.result), _fmt(r.reaction_time_ms),
                          _fmt(r.completion_time_ms), _fmt(r.error_distance, 1), _fmt(r.target_distance, 0),
                          moved, tr(r.validity_label())]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column != 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, column, item)

    def _export(self) -> None:
        if self.analysis is None:
            return
        try:
            folder = export_session(self.context.repository, self.analysis, self.context.settings.exports_dir)
        except Exception as exc:  # noqa: BLE001
            log.exception("export_failed")
            self.banner.show_message("Export failed: {error}", Banner.Kind.ERROR, error=exc)
            return
        self.banner.show_message("Exported to {folder}", Banner.Kind.SUCCESS, folder=folder)
