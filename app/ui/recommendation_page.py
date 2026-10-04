"""Recommendation screen (Milestone 10).

Shows the player's profile, which placeholder rules applied, and the ranked
candidate crosshairs of a stored recommendation run. Everything shown is read
back from the stored run so earlier runs can be reviewed unchanged.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from app.analysis.metrics import METRICS, TASK_METRICS, format_metric
from app.analysis.profile import PROFILE_RULE, build_profile
from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.data.models import ConditionEvaluation, ExperimentType
from app.data.repository import RepositoryError
from app.experiment.evaluation import EvaluationError, start_evaluation
from app.experiment.protocol import build_protocol
from app.recommendation.engine import COMPONENT_LABELS, COMPONENTS, score_candidates, store_recommendation
from app.utils.validators import ValidationError
from app.ui.components import (
    Banner,
    BasePage,
    Card,
    PageId,
    combo_box,
    label,
    primary_button,
    secondary_button,
)
from app.ui.crosshair_widgets import parameter_rows, thumbnail
from app.i18n import display, is_japanese, set_tr_text, tr
from app.ui.session_format import TASK_LABELS, task_label
from app.utils.logging import get_logger

log = get_logger("ui.recommendation")

STATUS_TEXT = {"applied": "Applied", "not applied": "Not applied", "no data": "No data"}


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


class RecommendationPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Recommendation",
            "Candidate crosshairs to try next, ranked by a rule-based score from your own baseline "
            "measurements. This is not a validated prediction: only a re-test can show a measured difference.",
            parent,
        )
        self.context = context
        self.recommendation: dict | None = None

        row = QHBoxLayout()
        self.generate_button = primary_button("Generate candidates")
        self.generate_button.clicked.connect(self.generate)
        self.run_combo = combo_box(360)
        self.run_combo.currentIndexChanged.connect(self._on_run_changed)
        row.addWidget(self.generate_button)
        row.addSpacing(16)
        row.addWidget(label("Stored runs", "mutedLabel"))
        row.addWidget(self.run_combo, 1)
        self.content.addLayout(row)

        self.banner = Banner()
        self.content.addWidget(self.banner)
        self.method_banner = Banner()
        self.content.addWidget(self.method_banner)

        self.profile_card = Card("Your baseline profile")
        self.profile_grid = QGridLayout()
        self.profile_grid.setHorizontalSpacing(24)
        self.profile_card.body.addLayout(self.profile_grid)
        self.profile_rule_label = label("", "faintLabel", wrap=True)
        set_tr_text(
            self.profile_rule_label,
            "Source rule: {rule} (placeholder). Aborted, practice, familiarization, standard and "
            "candidate sessions are not used.",
            rule=PROFILE_RULE,
        )
        self.profile_card.body.addWidget(self.profile_rule_label)
        self.content.addWidget(self.profile_card)

        self.rules_card = Card("Rules (placeholder hypotheses, not validated)")
        self.rules_grid = QGridLayout()
        self.rules_grid.setHorizontalSpacing(18)
        self.rules_card.body.addLayout(self.rules_grid)
        self.weights_label = label("", "mutedLabel", wrap=True)
        self.rules_card.body.addWidget(self.weights_label)
        self.content.addWidget(self.rules_card)

        self.candidates_card = Card("Candidates to try")
        self.candidates_box = QVBoxLayout()
        self.candidates_box.setSpacing(12)
        self.candidates_card.body.addLayout(self.candidates_box)
        self.content.addWidget(self.candidates_card)
        self.finish_layout()

    # ------------------------------------------------------------- navigation
    def on_page_shown(self) -> None:
        self.reload_runs()

    def reload_runs(self, select_id: int | None = None) -> None:
        player = self.context.current_player
        self.generate_button.setEnabled(player is not None)
        runs = self.context.repository.list_recommendations(player.player_id) if player else []
        current = select_id if select_id is not None else self.run_combo.currentData()
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        for run in runs:
            self.run_combo.addItem(
                f"#{run['recommendation_id']}  {run['created_at'][:19].replace('T', ' ')}  "
                + tr("({version}, {count} candidates)", version=run["method_version"],
                     count=len(run["candidates"])),
                run["recommendation_id"])
        self.run_combo.blockSignals(False)

        if player is None:
            self._show_empty("Select or create a participant on the Setup page first.")
            return
        if not runs:
            self._show_empty("No recommendation generated yet for participant "
                             "{player_id}. Complete at least one baseline assessment, then press "
                             "“Generate candidates”.", player_id=player.player_id)
            return
        index = self.run_combo.findData(current)
        self.run_combo.setCurrentIndex(index if index >= 0 else 0)
        self._on_run_changed(self.run_combo.currentIndex())

    def _show_empty(self, message: str, **values: object) -> None:
        self.recommendation = None
        self.banner.show_message(message, Banner.Kind.INFO, **values)
        self.method_banner.clear_message()
        for card in (self.profile_card, self.rules_card, self.candidates_card):
            card.setVisible(False)

    # ---------------------------------------------------------------- actions
    def _debug_mode(self) -> bool:
        try:
            return build_protocol(self.context.research).debug_task_selection_enabled
        except ValidationError:
            return False

    def _evaluations(self) -> list[ConditionEvaluation]:
        player = self.context.current_player
        return self.context.repository.list_condition_evaluations(player.player_id) if player else []

    def generate(self) -> None:
        player = self.context.current_player
        if player is None:
            return
        repo = self.context.repository
        if self._evaluations() and not self._debug_mode():
            self.banner.show_message(
                "A crosshair evaluation already uses a recommendation run of this participant. The "
                "recommendation is generated once per cycle and later sessions do not change it.",
                Banner.Kind.WARNING)
            return
        try:
            profile = build_profile(repo, player.player_id)
            if not profile.tasks:
                self.banner.show_message(
                    "No completed baseline session yet. Run at least one assessment with the standard "
                    "crosshair first.", Banner.Kind.WARNING)
                return
            result = score_candidates(repo, self.context.research, self.context.baseline_crosshair, profile)
            if not result.ranked:
                self.banner.show_message(
                    "The crosshair database has no candidates that differ from the baseline. Import or "
                    "update candidates on the Crosshair page first.", Banner.Kind.WARNING)
                return
            recommendation_id = store_recommendation(repo, result)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never silent
            log.exception("recommendation_failed")
            self.banner.show_message("Could not generate candidates: {error}", Banner.Kind.ERROR, error=exc)
            return
        log.info("recommendation_stored id=%s player=%s", recommendation_id, player.player_id)
        self.reload_runs(recommendation_id)

    def _try_candidate(self, crosshair_id: int) -> None:
        rec = self.recommendation
        if rec is None:
            return
        try:
            self.context.repository.mark_candidate_selected(rec["recommendation_id"], crosshair_id)
        except RepositoryError as exc:
            self.banner.show_message(str(exc), Banner.Kind.WARNING)
            return
        self.navigate_requested.emit(f"{PageId.ASSESSMENT}:candidate:{rec['recommendation_id']}:{crosshair_id}")

    def select_for_evaluation(self, crosshair_id: int, confirm: bool = True) -> ConditionEvaluation | None:
        """Fix one candidate for the crosshair evaluation (cannot be changed afterwards)."""
        rec = self.recommendation
        player = self.context.current_player
        if rec is None or player is None:
            return None
        if confirm:
            answer = QMessageBox.question(
                self, tr("Select for crosshair evaluation"),
                tr("Use this crosshair for the crosshair evaluation? The selection cannot be changed afterwards."),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
        try:
            evaluation = start_evaluation(self.context.repository, build_protocol(self.context.research),
                                          player.player_id, rec["recommendation_id"], crosshair_id)
        except (EvaluationError, RepositoryError, ValidationError) as exc:
            self.banner.show_message(str(exc), Banner.Kind.WARNING)
            return None
        self.reload_runs(rec["recommendation_id"])
        self.banner.show_message("Candidate selected. Next assessment: Crosshair evaluation", Banner.Kind.SUCCESS)
        self.navigate_requested.emit(str(PageId.ASSESSMENT))
        return evaluation

    # --------------------------------------------------------------- display
    def _on_run_changed(self, index: int) -> None:
        rec_id = self.run_combo.itemData(index)
        if rec_id is None:
            return
        self.recommendation = self.context.repository.get_recommendation(rec_id)
        if self.recommendation is None:
            return
        for card in (self.profile_card, self.rules_card, self.candidates_card):
            card.setVisible(True)
        self._show_banners()
        self._show_profile()
        self._show_rules()
        self._show_candidates()

    def _show_banners(self) -> None:
        rec = self.recommendation
        weights = rec["weights"]
        missing = rec["profile"].get("missing_tasks", [])
        if missing:
            names = ", ".join(task_label(t) for t in missing)
            self.banner.show_message(
                "No completed baseline session for: {names}. Rules that need these tasks were not applied. "
                "Run those assessments and generate again to include them.", Banner.Kind.WARNING, names=names)
        else:
            self.banner.clear_message()
        confirmed = weights.get("confirmed", False)
        text = tr("Method: {method} ({version}). Components, weights, thresholds and rules "
                  "are configurable in research_parameters.json and have not been validated.",
                  method=rec["method"], version=rec["method_version"])
        if not confirmed:
            text += " " + tr("Research decision required: these are placeholder values (confirmed = false).")
        self.method_banner.show_message(text, Banner.Kind.INFO)

    def _show_profile(self) -> None:
        _clear(self.profile_grid)
        tasks = self.recommendation["profile"].get("tasks", {})
        for row, task in enumerate(ExperimentType):
            self.profile_grid.addWidget(label(TASK_LABELS[str(task)], "sectionTitle"), row, 0)
            data = tasks.get(str(task))
            if data is None:
                self.profile_grid.addWidget(label("no completed baseline session", "faintLabel"), row, 1)
                continue
            parts = [f"{tr(METRICS[name].label)}: {format_metric(name, data['metrics'].get(name))}"
                     for name in TASK_METRICS[task] if name in data["metrics"]][:4]
            text = tr("Session {session_id}", session_id=data["session_id"]) + "  ·  " + "  ·  ".join(parts)
            self.profile_grid.addWidget(label(text, wrap=True), row, 1)
        self.profile_grid.setColumnStretch(1, 1)

    def _show_rules(self) -> None:
        _clear(self.rules_grid)
        weights = self.recommendation["weights"]
        for column, title in enumerate(("Rule", "Condition", "Your value", "Weight change", "Status")):
            self.rules_grid.addWidget(label(title, "mutedLabel"), 0, column)
        for row, rule in enumerate(weights.get("rules", []), start=1):
            _, _, metric = rule["metric"].partition(".")
            definition = METRICS.get(metric)
            condition = (f"{tr(TASK_LABELS.get(rule['metric'].split('.')[0], ''))}: "
                         f"{tr(definition.label) if definition else metric} {rule['op']} "
                         f"{format_metric(metric, rule['threshold'])}")
            value = "–" if rule["value"] is None else format_metric(metric, rule["value"])
            change = ", ".join(f"{tr(COMPONENT_LABELS.get(k, k))} {v:+g}" for k, v in rule["adjust"].items())
            status = label(STATUS_TEXT.get(rule["status"], rule["status"]))
            status.setObjectName("successLabel" if rule["status"] == "applied" else "faintLabel")
            for column, widget in enumerate((label(rule["id"], wrap=True), label(condition, wrap=True),
                                             label(value), label(change, wrap=True), status)):
                self.rules_grid.addWidget(widget, row, column)
        self.rules_grid.setColumnStretch(1, 1)
        effective = weights.get("effective", {})
        excluded = (tr(" ({count} excluded as duplicates)", count=len(weights["excluded"]))
                    if weights.get("excluded") else "")
        self.weights_label.setText(tr(
            "Weights used: {weights}. Candidate pool: {pool} crosshairs{excluded}. "
            "Score = weighted mean of the component scores (0–1).",
            weights=", ".join(f"{tr(COMPONENT_LABELS[c])} {effective.get(c, 0):g}" for c in COMPONENTS),
            pool=weights.get("pool_size", "?"),
            excluded=excluded,
        ))

    def _show_candidates(self) -> None:
        _clear(self.candidates_box)
        candidates = self.recommendation["candidates"]
        if not candidates:
            self.candidates_box.addWidget(label("This run has no candidates.", "faintLabel"))
            return
        sources = {listing.crosshair.crosshair_id: listing.source
                   for listing in self.context.repository.list_source_listings() if listing.crosshair}
        for candidate in candidates:
            record = self.context.repository.get_crosshair(candidate["crosshair_id"])
            if record is None:
                continue
            self.candidates_box.addWidget(self._candidate_card(candidate, record, sources.get(record.crosshair_id)))

    def _explanation(self, candidate: dict) -> str:
        """Stored English explanation, or a Japanese rendering of the same stored values.

        The stored explanation text is never modified; the Japanese text is rebuilt
        from the stored component scores, effective weights and rule outcomes.
        """
        if not is_japanese() or self.recommendation is None:
            return candidate["explanation"]
        weights = self.recommendation.get("weights", {})
        effective = weights.get("effective")
        scores = candidate.get("component_scores") or {}
        if not effective or any(c not in scores or c not in effective for c in COMPONENTS):
            return candidate["explanation"]
        parts = ", ".join(
            tr("{component} {score} (weight {weight})", component=tr(COMPONENT_LABELS[c]),
               score=f"{scores[c]:.2f}", weight=f"{effective[c]:g}")
            for c in COMPONENTS
        )
        text = tr("Score {score} = weighted mean of {parts}.", score=f"{candidate['score']:.3f}", parts=parts)
        fired = [rule for rule in weights.get("rules", []) if rule.get("status") == "applied"]
        if fired:
            described = []
            for rule in fired:
                _, _, metric = rule["metric"].partition(".")
                definition = METRICS.get(metric)
                shown = format_metric(metric, rule["value"]) if rule["value"] is not None else tr("no data")
                described.append(
                    f"{rule['id']} ({tr(definition.label) if definition else metric} {shown} {rule['op']} "
                    f"{format_metric(metric, rule['threshold'])})")
            text += " " + tr("Rules that changed the weights: {rules}.", rules="; ".join(described))
        else:
            text += " " + tr("No rule changed the base weights.")
        return text

    def _candidate_card(self, candidate: dict, record, source) -> Card:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(18)
        config = CrosshairConfig.from_record(record)
        thumb = QLabel()
        pixmap = thumbnail(config.to_shape(), self.context.research, self.devicePixelRatioF())
        if pixmap is not None:
            thumb.setPixmap(pixmap)
        thumb.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(4)
        title = tr("Candidate {rank}: {name}", rank=candidate["rank"], name=record.name)
        if candidate.get("selected_by_player"):
            title += tr("  (selected to try)")
        info.addWidget(label(title, "sectionTitle", wrap=True))
        origin = []
        if source is not None:
            if source.source_player:
                origin.append(tr("from {player}", player=source.source_player))
            origin.append(tr("source: {name}", name=source.source_name))
        origin.append(tr("mapping fidelity: {fidelity}",
                         fidelity=display(record.fidelity) if record.fidelity else tr("n/a")))
        info.addWidget(label("  ·  ".join(origin), "mutedLabel", wrap=True))
        info.addWidget(label("  ·  ".join(f"{tr(n)}: {v}" for n, v in parameter_rows(config)), wrap=True))
        scores = candidate["component_scores"]
        info.addWidget(label(
            tr("Candidate score {score}", score=f"{candidate['score']:.3f}") + "  —  " + ", ".join(
                f"{tr(COMPONENT_LABELS[c])} {scores.get(c, 0):.2f}" for c in COMPONENTS), "mutedLabel", wrap=True))
        info.addWidget(label(self._explanation(candidate), "faintLabel", wrap=True))
        row.addLayout(info, 1)

        buttons = QVBoxLayout()
        evaluations = self._evaluations()
        fixed = next((e for e in evaluations if e.recommendation_id == self.recommendation["recommendation_id"]),
                     None)
        if fixed is not None and fixed.selected_candidate_id == record.crosshair_id:
            buttons.addWidget(label("Selected for crosshair evaluation", "successLabel"))
        select = primary_button("Select for crosshair evaluation")
        select.setEnabled(not evaluations)
        select.clicked.connect(lambda _=False, cid=record.crosshair_id: self.select_for_evaluation(cid))
        buttons.addWidget(select)
        button = secondary_button("Try this candidate")
        button.clicked.connect(lambda _=False, cid=record.crosshair_id: self._try_candidate(cid))
        button.setVisible(self._debug_mode())
        buttons.addWidget(button)
        buttons.addStretch(1)
        row.addLayout(buttons)
        card.body.addLayout(row)
        return card
