"""Comparison screen (Milestone 12): candidate session vs its linked baseline,
and (Phase 5) the three conditions of a crosshair evaluation cycle.

Shows measured differences only (see ``app.analysis.comparison``). Wording is
limited to "higher / lower"; no causal claims are made.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.analysis.comparison import (
    CONDITION_CSV_HEADER,
    CONDITION_LABELS,
    CSV_HEADER,
    ConditionComparison,
    SessionComparison,
    compare_conditions,
    compare_sessions,
)
from app.analysis.export import export_rows
from app.analysis.metrics import ANALYSIS_VERSION, METRICS, format_metric
from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.data.models import NON_ANALYSED_STAGES, Condition, ExperimentType, TrialResult
from app.ui.charts import BASELINE_COLOR, CANDIDATE_COLOR, ChartCanvas
from app.ui.components import Banner, BasePage, Card, PageId, combo_box, label, secondary_button
from app.ui.crosshair_widgets import thumbnail
from app.i18n import display, set_tr_text, tr, tr_message
from app.ui.session_format import task_label
from app.utils.logging import get_logger

log = get_logger("ui.comparison")

COLUMNS = ["Metric", "Baseline", "Candidate", "Difference (candidate − baseline)", "% difference",
           "Measured direction", "Desirable direction"]
CONDITION_COLUMNS = ["Metric", "Baseline", "Standard", "Candidate", "Baseline → Standard",
                     "Baseline → Candidate", "Standard → Candidate"]


class ComparisonPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Comparison",
            "Measured differences between a candidate re-test session and the baseline session it is "
            "linked to. Differences describe these two sessions only.",
            parent,
        )
        self.context = context
        self.comparison: SessionComparison | None = None

        row = QHBoxLayout()
        self.session_combo = combo_box(420)
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)
        self.export_button = secondary_button("Export CSV")
        self.export_button.clicked.connect(self._export)
        row.addWidget(label("Candidate session", "mutedLabel"))
        row.addWidget(self.session_combo, 1)
        row.addWidget(self.export_button)
        self.content.addLayout(row)

        self.banner = Banner()
        self.content.addWidget(self.banner)
        self.caveat_banner = Banner()
        self.content.addWidget(self.caveat_banner)

        self.pair_card = Card("Sessions compared")
        pair_row = QHBoxLayout()
        pair_row.setSpacing(24)
        self.baseline_box = QVBoxLayout()
        self.candidate_box = QVBoxLayout()
        pair_row.addLayout(self.baseline_box, 1)
        pair_row.addLayout(self.candidate_box, 1)
        self.pair_card.body.addLayout(pair_row)
        self.content.addWidget(self.pair_card)

        self.table_card = Card("Metrics")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(320)
        self.table_card.body.addWidget(self.table)
        self.analysis_note = label("", "faintLabel", wrap=True)
        set_tr_text(
            self.analysis_note,
            "Analysis version {version}. pp = percentage points. “% difference” is only given for "
            "times and distances. “Desirable direction” states which direction the metric is defined to "
            "favour; it is not a judgement of the crosshair.",
            version=ANALYSIS_VERSION,
        )
        self.table_card.body.addWidget(self.analysis_note)
        self.content.addWidget(self.table_card)

        self.chart_card = Card("Per-trial values")
        self.chart = ChartCanvas(260)
        self.chart_card.body.addWidget(self.chart)
        self.content.addWidget(self.chart_card)

        self.condition_comparison: ConditionComparison | None = None
        self.evaluation_card = Card("Crosshair evaluation: three conditions")
        evaluation_row = QHBoxLayout()
        self.evaluation_combo = combo_box(320)
        self.evaluation_combo.currentIndexChanged.connect(self._on_evaluation_changed)
        self.evaluation_task_combo = combo_box(200)
        for task in ExperimentType:
            self.evaluation_task_combo.addItem(task_label(task), str(task))
        self.evaluation_task_combo.currentIndexChanged.connect(self._on_evaluation_changed)
        self.evaluation_export_button = secondary_button("Export CSV")
        self.evaluation_export_button.clicked.connect(self._export_evaluation)
        evaluation_row.addWidget(label("Evaluation", "mutedLabel"))
        evaluation_row.addWidget(self.evaluation_combo, 1)
        evaluation_row.addWidget(self.evaluation_task_combo)
        evaluation_row.addWidget(self.evaluation_export_button)
        self.evaluation_card.body.addLayout(evaluation_row)
        self.evaluation_status = label("", "mutedLabel", wrap=True)
        self.evaluation_card.body.addWidget(self.evaluation_status)
        self.evaluation_caveats = Banner()
        self.evaluation_card.body.addWidget(self.evaluation_caveats)
        self.evaluation_table = QTableWidget(0, len(CONDITION_COLUMNS))
        self.evaluation_table.setHorizontalHeaderLabels([tr(c) for c in CONDITION_COLUMNS])
        self.evaluation_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.evaluation_table.setWordWrap(True)
        self.evaluation_table.verticalHeader().setVisible(False)
        self.evaluation_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.evaluation_table.horizontalHeader().setStretchLastSection(True)
        self.evaluation_table.setMinimumHeight(320)
        self.evaluation_card.body.addWidget(self.evaluation_table)
        self.evaluation_card.body.addWidget(label(
            "Descriptive differences of single sessions only (no statistical test). “%” is only given for "
            "times and distances; pp = percentage points.", "faintLabel", wrap=True))
        self.content.addWidget(self.evaluation_card)
        self.finish_layout()

    # ------------------------------------------------------------- navigation
    def on_page_shown(self) -> None:
        self.reload_sessions()
        self.reload_evaluations()

    def show_section(self, section: str) -> None:
        kind, _, rest = section.partition(":")
        if kind == "evaluation" and rest.isdigit():
            index = self.evaluation_combo.findData(int(rest))
            if index >= 0:
                self.evaluation_combo.setCurrentIndex(index)
                self._on_evaluation_changed()
            return
        if section.isdigit():
            index = self.session_combo.findData(int(section))
            if index >= 0:
                self.session_combo.setCurrentIndex(index)
                if self.comparison is None or self.comparison.candidate.session.session_id != int(section):
                    self._on_session_changed(index)

    def reload_sessions(self) -> None:
        current = self.session_combo.currentData()
        player = self.context.current_player
        sessions = self.context.repository.list_sessions(
            player.player_id if player else None, condition=Condition.CANDIDATE)
        sessions = [
            session for session in sessions
            if session.assessment_stage not in NON_ANALYSED_STAGES
            and session.parent_session_id is not None
        ]
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        for s in sessions:
            crosshair = self.context.repository.get_crosshair(s.crosshair_id)
            text = (f"#{s.session_id}  ·  {task_label(s.experiment_type)}  ·  "
                    f"{crosshair.name if crosshair else s.crosshair_id}  ·  "
                    + tr("vs baseline #{session_id}", session_id=s.parent_session_id) + "  ·  "
                    f"{(s.started_at or '')[:16].replace('T', ' ')}")
            if str(s.status) != "completed":
                text += f"  [{display(s.status)}]"
            self.session_combo.addItem(text, s.session_id)
        self.session_combo.blockSignals(False)
        has_sessions = bool(sessions)
        for widget in (self.pair_card, self.table_card, self.chart_card, self.export_button):
            widget.setVisible(has_sessions)
        if not has_sessions:
            self.comparison = None
            self.caveat_banner.clear_message()
            self.banner.show_message(
                "No candidate sessions yet. On the Recommendation page choose “Try this candidate”, then run "
                "the same task again on the Aim Assessment page; the session will appear here next to its "
                "baseline.", Banner.Kind.INFO)
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
            self.comparison = compare_sessions(self.context.repository, session_id)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            log.exception("comparison_failed session_id=%s", session_id)
            self.comparison = None
            self.banner.show_message("Could not compare session {session_id}: {error}", Banner.Kind.ERROR,
                                     session_id=session_id, error=exc)
            return
        self.banner.clear_message()
        # Caveats are stored/exported in English; only their display is translated.
        self.caveat_banner.show_message(
            tr("Caveats:") + " " + " ".join(tr_message(c) for c in self.comparison.caveats),
            Banner.Kind.WARNING,
        )
        self._show_pair()
        self._show_table()
        self._show_chart()

    def _session_box(self, box: QVBoxLayout, title: str, analysis) -> None:
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        session = analysis.session
        crosshair = self.context.repository.get_crosshair(session.crosshair_id)
        box.addWidget(label(title, "sectionTitle"))
        row = QHBoxLayout()
        holder = QWidget()
        holder.setLayout(row)
        thumb = QLabel()
        if crosshair is not None:
            pixmap = thumbnail(CrosshairConfig.from_record(crosshair).to_shape(), self.context.research,
                               self.devicePixelRatioF())
            if pixmap is not None:
                thumb.setPixmap(pixmap)
        row.addWidget(thumb)
        details = [tr("Session #{session_id}", session_id=session.session_id)
                   + f"  ·  {(session.started_at or '')[:16].replace('T', ' ')}",
                   tr("Crosshair: {name}", name=crosshair.name if crosshair else session.crosshair_id),
                   tr("Status: {status}  ·  {count} trials", status=display(session.status),
                      count=len(analysis.rows))]
        if session.recommendation_id:
            details.append(tr("From recommendation #{recommendation_id}",
                              recommendation_id=session.recommendation_id))
        text = label("\n".join(details), "mutedLabel", wrap=True)
        row.addWidget(text, 1)
        box.addWidget(holder)
        open_button = secondary_button("Open results")
        open_button.clicked.connect(
            lambda _=False, sid=session.session_id: self.navigate_requested.emit(f"{PageId.RESULTS}:{sid}"))
        box.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)

    def _show_pair(self) -> None:
        self._session_box(self.baseline_box, "Baseline (standard crosshair)", self.comparison.baseline)
        self._session_box(self.candidate_box, "Candidate", self.comparison.candidate)

    def _show_table(self) -> None:
        rows = self.comparison.table_rows()
        self.table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                # Display-only translation (metric label, direction words); exports stay English.
                item = QTableWidgetItem(tr(value) if c in (0, 5, 6) else value)
                if c:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, c, item)

    def _show_chart(self) -> None:
        comp = self.comparison
        ax = self.chart.new_axes()
        tracking = comp.task == ExperimentType.TRACKING
        for analysis, name, color, marker in ((comp.baseline, "baseline", BASELINE_COLOR, "o"),
                                              (comp.candidate, "candidate", CANDIDATE_COLOR, "s")):
            if tracking:
                points = [(i, (r.on_target_ratio or 0) * 100) for i, r in enumerate(analysis.rows, start=1)]
            else:
                points = [(i, r.completion_time_ms) for i, r in enumerate(analysis.rows, start=1)
                          if r.result == TrialResult.HIT and r.completion_time_ms is not None]
            if points:
                ax.plot(*zip(*points), color=color, marker=marker, markersize=4, linewidth=1,
                        label=display(name))
        ax.set_xlabel(tr("trial / target (order in session)"))
        ax.set_ylabel(tr("time on target (%)" if tracking else "completion time, hits (ms)"))
        self.chart_card.set_title(
            "Time on target per trial" if tracking else "Completion time per hit")
        self.chart.finish(ax)

    # ------------------------------------------------------ crosshair evaluation
    def reload_evaluations(self) -> None:
        current = self.evaluation_combo.currentData()
        player = self.context.current_player
        evaluations = self.context.repository.list_condition_evaluations(player.player_id if player else None)
        self.evaluation_combo.blockSignals(True)
        self.evaluation_combo.clear()
        for e in evaluations:
            self.evaluation_combo.addItem(
                tr("Evaluation #{evaluation_id}  ·  recommendation #{recommendation_id}  ·  {status}",
                   evaluation_id=e.evaluation_id, recommendation_id=e.recommendation_id,
                   status=display(e.status)), e.evaluation_id)
        self.evaluation_combo.blockSignals(False)
        self.evaluation_card.setVisible(bool(evaluations))
        if not evaluations:
            self.condition_comparison = None
            return
        index = self.evaluation_combo.findData(current)
        self.evaluation_combo.setCurrentIndex(index if index >= 0 else 0)
        self._on_evaluation_changed()

    def _on_evaluation_changed(self, *_args) -> None:
        evaluation_id = self.evaluation_combo.currentData()
        task = self.evaluation_task_combo.currentData()
        if evaluation_id is None or task is None:
            return
        try:
            comp = compare_conditions(self.context.repository, evaluation_id, task)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            log.exception("condition_comparison_failed evaluation_id=%s", evaluation_id)
            self.condition_comparison = None
            self.banner.show_message("Could not compare evaluation {evaluation_id}: {error}", Banner.Kind.ERROR,
                                     evaluation_id=evaluation_id, error=exc)
            return
        self.condition_comparison = comp
        e = comp.evaluation
        sessions = "  ·  ".join(
            f"{tr(CONDITION_LABELS[c])}: " + (f"#{a.session.session_id}" if a else tr("not recorded"))
            for c, a in comp.analyses.items())
        self.evaluation_status.setText(
            tr("Order {group} ({order})  ·  selected candidate #{candidate}  ·  protocol {protocol}",
               group=e.condition_order_group,
               order=" → ".join(tr(CONDITION_LABELS[Condition(c)]) for c in e.condition_order),
               candidate=e.selected_candidate_id, protocol=e.protocol_version or "–")
            + "\n" + sessions)
        self.evaluation_caveats.show_message(
            tr("Caveats:") + " " + " ".join(tr_message(c) for c in comp.caveats), Banner.Kind.WARNING)
        metric_names = [m.name for m in comp.pairs[0].metrics]
        self.evaluation_table.setRowCount(len(metric_names))
        for r, name in enumerate(metric_names):
            values = [tr(METRICS[name].label)]
            for condition in CONDITION_LABELS:
                analysis = comp.analyses[condition]
                values.append(format_metric(name, analysis.metrics.get(name)) if analysis else "–")
            for pair in comp.pairs:
                template, parts = pair.metrics[r].summary(pair.reference_label, pair.compared_label)
                parts = {k: tr(v) if k in ("other", "reference") else v for k, v in parts.items()}
                values.append(tr(template, **parts))
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if 0 < c < 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.evaluation_table.setItem(r, c, item)
        self.evaluation_table.resizeRowsToContents()

    def _export_evaluation(self) -> None:
        comp = self.condition_comparison
        if comp is None:
            return
        try:
            path = export_rows(self.context.settings.exports_dir,
                               f"condition_comparison_evaluation{comp.evaluation.evaluation_id}_{comp.task}",
                               CONDITION_CSV_HEADER + ["caveats"],
                               [row + [json.dumps(comp.caveats, ensure_ascii=False)] for row in comp.csv_rows()])
        except Exception as exc:  # noqa: BLE001
            log.exception("condition_comparison_export_failed")
            self.banner.show_message("Export failed: {error}", Banner.Kind.ERROR, error=exc)
            return
        self.banner.show_message("Exported to {folder}", Banner.Kind.SUCCESS, folder=path)

    def _export(self) -> None:
        if self.comparison is None:
            return
        c = self.comparison
        try:
            path = export_rows(self.context.settings.exports_dir,
                               f"comparison_{c.candidate.session.session_id}_vs_{c.baseline.session.session_id}",
                               CSV_HEADER + ["caveats"],
                               [row + [json.dumps(c.caveats, ensure_ascii=False)] for row in c.csv_rows()])
        except Exception as exc:  # noqa: BLE001
            log.exception("comparison_export_failed")
            self.banner.show_message("Export failed: {error}", Banner.Kind.ERROR, error=exc)
            return
        self.banner.show_message("Exported to {folder}", Banner.Kind.SUCCESS, folder=path)
