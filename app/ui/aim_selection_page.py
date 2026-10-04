"""Aim assessment selection: Flick Aim, Tracking and Target Switching.

The crosshair selector chooses between a baseline session (standard
crosshair) and a candidate re-test (Milestone 11) with a crosshair from the
player's latest recommendation. A candidate session is linked to the latest
completed baseline session of the same task (``parent_session_id``, placeholder
rule) and uses the same task parameters and seed, so the target sequence is
the same as in the baseline.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.data.models import (
    AssessmentStage,
    AssessmentStatus,
    Condition,
    CrosshairRole,
    ExperimentType,
    SessionStatus,
    TaskAssessment,
    TaskOrderMode,
)
from app.data.repository import RepositoryError
from app.experiment.protocol import build_protocol
from app.experiment.task_order import parse_task_order
from app.i18n import tr
from app.ui.components import BasePage, Banner, Card, PageId, combo_box, label, primary_button
from app.ui.crosshair_widgets import parameter_rows, thumbnail
from app.ui.session_format import task_label, task_order_text
from app.ui.experiment_window import ExperimentWindow, RunSetup
from app.ui.flick_window import FlickExperimentWindow
from app.ui.switching_window import SwitchingExperimentWindow
from app.ui.tracking_window import TrackingExperimentWindow
from app.utils.validators import ValidationError

TASKS: dict[ExperimentType, tuple[str, str, type[ExperimentWindow]]] = {
    ExperimentType.FLICK: (
        "Flick Aim",
        "A single target appears. Move the crosshair onto it and click as quickly and "
        "accurately as possible.",
        FlickExperimentWindow,
    ),
    ExperimentType.TRACKING: (
        "Tracking",
        "A target moves along a reproducible path. Keep the crosshair on the target for "
        "the duration of the trial.",
        TrackingExperimentWindow,
    ),
    ExperimentType.SWITCHING: (
        "Target Switching",
        "Several targets are shown. Click the highlighted one; the next target is "
        "highlighted immediately.",
        SwitchingExperimentWindow,
    ),
}

PARENT_RULE = "latest completed baseline session of the same task"


class AimSelectionPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(
            "Aim Assessment",
            "Choose an assessment task. During a task the screen shows only the target, "
            "the crosshair and a controlled background.",
            parent,
        )
        self.context = context
        self.experiment_window: ExperimentWindow | None = None
        self._last_session_id = 0
        self._controlled_window = False
        self.active_assessment: TaskAssessment | None = None
        self._has_recommendation = False
        self.banner = Banner()
        self.content.addWidget(self.banner)
        self.parameter_banner = Banner()
        self.content.addWidget(self.parameter_banner)

        crosshair_card = Card("Crosshair for this session")
        crosshair_row = QHBoxLayout()
        crosshair_row.setSpacing(16)
        self.crosshair_thumb = QLabel()
        crosshair_row.addWidget(self.crosshair_thumb)
        column = QVBoxLayout()
        self.crosshair_combo = combo_box(420)
        self.crosshair_combo.currentIndexChanged.connect(self._on_crosshair_changed)
        column.addWidget(self.crosshair_combo)
        self.crosshair_params = label("", "mutedLabel", wrap=True)
        column.addWidget(self.crosshair_params)
        self.crosshair_note = label("", "faintLabel", wrap=True)
        column.addWidget(self.crosshair_note)
        column.addStretch(1)
        crosshair_row.addLayout(column, 1)
        crosshair_card.body.addLayout(crosshair_row)
        self.content.addWidget(crosshair_card)

        self.controlled_card = Card("Controlled task-order assessment")
        self.assessment_status = label("", "mutedLabel", wrap=True)
        self.controlled_card.body.addWidget(self.assessment_status)
        self.controlled_button = primary_button("Start controlled assessment")
        self.controlled_button.clicked.connect(self.start_or_resume_assessment)
        self.controlled_card.body.addWidget(self.controlled_button)
        self.content.addWidget(self.controlled_card)

        self.debug_card = Card("Researcher/developer mode — individual task launch")
        self.debug_card.body.addWidget(label(
            "Non-experimental debugging only. These buttons do not constitute a controlled "
            "three-task assessment.", "faintLabel", wrap=True))
        self.debug_order_label = label("", "faintLabel", wrap=True)
        self.debug_card.body.addWidget(self.debug_order_label)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.start_buttons: dict[ExperimentType, QPushButton] = {}
        self.link_labels: dict[ExperimentType, QLabel] = {}
        for task, (title, description, _window) in TASKS.items():
            card = Card(title)
            card.body.addWidget(label(description, "mutedLabel", wrap=True))
            card.body.addStretch(1)
            link = label("", "faintLabel", wrap=True)
            card.body.addWidget(link)
            button = primary_button("Start")
            button.clicked.connect(lambda _checked=False, t=task: self.start_task(t))
            card.body.addWidget(button)
            self.start_buttons[task] = button
            self.link_labels[task] = link
            row.addWidget(card, 1)
        self.debug_card.body.addLayout(row)
        self.content.addWidget(self.debug_card)
        self.finish_layout()

    # ------------------------------------------------------------- navigation
    def on_page_shown(self) -> None:
        player = self.context.current_player
        if player is None:
            self.banner.show_message(
                "No participant selected. Complete Player Setup before starting an assessment.",
                Banner.Kind.WARNING,
            )
        else:
            self.banner.show_message(
                "Participant: {player_id}", Banner.Kind.INFO, player_id=player.player_id
            )
            if player.task_order_group is None:
                player = self.context.repository.save_player(player)
                self.context.set_current_player(player)
        unconfirmed = [
            task_label(task) for task in TASKS
            if not self.context.research.task_parameters(task).get("confirmed", False)
        ]
        if unconfirmed:
            self.parameter_banner.show_message(
                "Placeholder task parameters ({tasks}) from research_parameters.json. "
                "Sessions are usable for testing; confirm the parameters before collecting research data.",
                Banner.Kind.WARNING,
                tasks=", ".join(unconfirmed),
            )
        else:
            self.parameter_banner.clear_message()
        self.reload_crosshairs()
        protocol = build_protocol(self.context.research)
        self.debug_card.setVisible(protocol.debug_task_selection_enabled)
        if player is not None:
            self.debug_order_label.setText(tr(
                "Assigned experimental order: {assigned}. Fixed debug order: {debug}.",
                assigned=task_order_text(player.task_order),
                debug=task_order_text(protocol.debug_fixed_task_order),
            ))
            active = self.context.repository.get_active_task_assessment(player.player_id)
            self.active_assessment = (
                self.context.repository.recover_task_assessment(active.assessment_id)
                if active is not None else None
            )
        else:
            self.active_assessment = None
        self._refresh_controlled_assessment()

    def show_section(self, section: str) -> None:
        kind, _, rest = section.partition(":")
        if kind != "candidate":
            return
        rec_id, _, crosshair_id = rest.partition(":")
        if rec_id.isdigit() and crosshair_id.isdigit():
            self.select_candidate(int(rec_id), int(crosshair_id))

    def select_candidate(self, recommendation_id: int, crosshair_id: int) -> None:
        for index in range(self.crosshair_combo.count()):
            run = self.crosshair_combo.itemData(index)
            if run is not None and run.recommendation_id == recommendation_id \
                    and run.crosshair.crosshair_id == crosshair_id:
                self.crosshair_combo.setCurrentIndex(index)
                return
        self.banner.show_message(
            "Candidate #{crosshair_id} of recommendation #{recommendation_id} is not in the latest "
            "recommendation run; generate a new recommendation to try it.", Banner.Kind.WARNING,
            crosshair_id=crosshair_id, recommendation_id=recommendation_id)

    # -------------------------------------------------------------- crosshair
    def reload_crosshairs(self) -> None:
        combo = self.crosshair_combo
        current: RunSetup | None = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(tr("Standard crosshair (baseline): {name}", name=self.context.baseline_crosshair.name),
                      RunSetup.baseline(self.context))
        repo = self.context.repository
        player = self.context.current_player
        runs = repo.list_recommendations(player.player_id) if player else []
        recommended: set[int] = set()
        if runs:
            latest = runs[0]
            combo.insertSeparator(combo.count())
            for candidate in latest["candidates"]:
                record = repo.get_crosshair(candidate["crosshair_id"])
                if record is None:
                    continue
                recommended.add(record.crosshair_id)
                combo.addItem(
                    tr("Recommended candidate {rank} (recommendation #{recommendation_id}): {name}",
                       rank=candidate["rank"], recommendation_id=latest["recommendation_id"],
                       name=record.name),
                    RunSetup(record, Condition.CANDIDATE, recommendation_id=latest["recommendation_id"]))
        for role, prefix in ((CrosshairRole.CUSTOM, "My crosshair"),
                             (CrosshairRole.CANDIDATE, "Database (not from a recommendation)")):
            records = [r for r in repo.list_crosshairs(role) if r.crosshair_id not in recommended]
            if records:
                combo.insertSeparator(combo.count())
            for record in records:
                combo.addItem(f"{tr(prefix)}: {record.name}", RunSetup(record, Condition.CANDIDATE))
        combo.blockSignals(False)
        self._has_recommendation = bool(runs)
        index = 0
        if current is not None:
            for i in range(combo.count()):
                run = combo.itemData(i)
                if (run is not None and run.recommendation_id == current.recommendation_id
                        and run.crosshair.crosshair_id == current.crosshair.crosshair_id
                        and run.condition == current.condition):
                    index = i
        combo.setCurrentIndex(index)
        self._on_crosshair_changed(index)

    def _on_crosshair_changed(self, index: int) -> None:
        run: RunSetup | None = self.crosshair_combo.itemData(index)
        if run is None:
            return
        config = CrosshairConfig.from_record(run.crosshair)
        pixmap = thumbnail(config.to_shape(), self.context.research, self.devicePixelRatioF())
        if pixmap is not None:
            self.crosshair_thumb.setPixmap(pixmap)
        self.crosshair_params.setText("  ·  ".join(f"{tr(n)}: {v}" for n, v in parameter_rows(config)))
        if run.condition == Condition.CANDIDATE:
            origin = tr("from your latest recommendation" if run.recommendation_id
                        else "your own choice (not from a recommendation; stored without a recommendation id)")
            self.crosshair_note.setText(tr(
                "Re-test with this crosshair, {origin}. The session is recorded as condition “candidate” and "
                "linked to the {rule} for comparison. Task parameters and seed are the same as the "
                "baseline.", origin=origin, rule=tr(PARENT_RULE)))
        else:
            hint = "" if self._has_recommendation else (" " + tr(
                "Other crosshairs can be chosen above; recommended candidates appear here after "
                "“Generate candidates” on the Recommendation page."))
            self.crosshair_note.setText(tr("Baseline session with the standard crosshair. Your profile and "
                                           "recommendations use completed baseline sessions.") + hint)
        self._update_task_cards()
        self._refresh_controlled_assessment()

    def parent_session_id(self, task: ExperimentType) -> int | None:
        player = self.context.current_player
        if player is None:
            return None
        sessions = self.context.repository.list_sessions(
            player.player_id, task, Condition.BASELINE, SessionStatus.COMPLETED)
        eligible = [
            session for session in sessions
            if session.assessment_stage != AssessmentStage.PRACTICE
        ]
        return eligible[0].session_id if eligible else None

    def _update_task_cards(self) -> None:
        run: RunSetup | None = self.crosshair_combo.currentData()
        player = self.context.current_player
        for task, button in self.start_buttons.items():
            link = self.link_labels[task]
            if run is None or run.condition == Condition.BASELINE:
                link.setText(tr("Crosshair: standard (baseline)"))
                button.setEnabled(player is not None)
                continue
            parent_id = self.parent_session_id(task)
            if parent_id is None:
                link.setText(tr("Needs a completed baseline session of this task before a candidate re-test."))
                button.setEnabled(False)
            else:
                link.setText(tr("Candidate re-test, compared with baseline session #{session_id}", session_id=parent_id))
                button.setEnabled(player is not None)

    def _refresh_controlled_assessment(self) -> None:
        """Participant-facing neutral status; group details stay in developer mode."""
        if not hasattr(self, "controlled_button"):
            return
        player = self.context.current_player
        if player is None:
            self.assessment_status.setText(tr("Select a participant before starting."))
            self.controlled_button.setEnabled(False)
            self.crosshair_combo.setEnabled(True)
            return
        assessment = self.active_assessment
        if assessment is not None and assessment.status == AssessmentStatus.IN_PROGRESS:
            template = ("Next practice:\n{task}" if assessment.stage == AssessmentStage.PRACTICE
                        else "Next assessment:\n{task}")
            task = task_label(ExperimentType(assessment.current_task))
            self.assessment_status.setText(tr(template, task=task))
            self.controlled_button.setText(tr("Resume controlled assessment"))
            self.controlled_button.setEnabled(self.experiment_window is None)
            self.crosshair_combo.setEnabled(False)
            return
        if assessment is not None and assessment.status == AssessmentStatus.COMPLETED:
            self.assessment_status.setText(tr("Controlled assessment complete."))
            self.controlled_button.setText(tr("Start another controlled assessment"))
        else:
            self.assessment_status.setText(tr(
                "Practice tasks and experimental tasks will follow the participant's "
                "stored counterbalanced order."))
            self.controlled_button.setText(tr("Start controlled assessment"))
        self.controlled_button.setEnabled(self.experiment_window is None)
        self.crosshair_combo.setEnabled(True)

    def start_or_resume_assessment(self) -> None:
        player = self.context.current_player
        if player is None or self.experiment_window is not None:
            return
        protocol = build_protocol(self.context.research)
        selected: RunSetup = self.crosshair_combo.currentData() or RunSetup.baseline(self.context)
        if self.active_assessment is not None \
                and self.active_assessment.status == AssessmentStatus.IN_PROGRESS:
            active_crosshair = self.context.repository.get_crosshair(
                self.active_assessment.crosshair_id
            )
            if active_crosshair is None:
                self.banner.show_message("The assessment crosshair no longer exists.", Banner.Kind.ERROR)
                return
            selected = RunSetup(
                active_crosshair, self.active_assessment.condition,
                recommendation_id=self.active_assessment.recommendation_id,
            )
        if selected.condition == Condition.CANDIDATE:
            missing = [task_label(task) for task in TASKS if self.parent_session_id(task) is None]
            if missing:
                self.banner.show_message(
                    "A controlled candidate assessment needs completed baseline sessions for all "
                    "three tasks. Missing: {tasks}.", Banner.Kind.WARNING, tasks=", ".join(missing),
                )
                return
        try:
            assessment = self.context.repository.start_or_resume_task_assessment(
                player.player_id, selected.condition, selected.crosshair.crosshair_id,
                selected.recommendation_id, protocol,
            )
        except RepositoryError as exc:
            self.banner.show_message(str(exc), Banner.Kind.WARNING)
            return
        self.active_assessment = assessment
        self._launch_assessment_task(assessment)

    def _launch_assessment_task(self, assessment: TaskAssessment) -> None:
        if assessment.current_task is None:
            return
        task = ExperimentType(assessment.current_task)
        crosshair = self.context.repository.get_crosshair(assessment.crosshair_id)
        if crosshair is None:
            self.banner.show_message("The assessment crosshair no longer exists.", Banner.Kind.ERROR)
            return
        parent_id = None
        if assessment.condition == Condition.CANDIDATE \
                and assessment.stage == AssessmentStage.EXPERIMENTAL:
            parent_id = self.parent_session_id(task)
            if parent_id is None:
                self.banner.show_message(
                    "Run a completed baseline {task} session before this candidate task.",
                    Banner.Kind.WARNING, task=task_label(task),
                )
                return
        order = assessment.order_for_stage()
        run = RunSetup(
            crosshair=crosshair,
            condition=assessment.condition,
            parent_session_id=parent_id,
            recommendation_id=assessment.recommendation_id,
            assessment_id=assessment.assessment_id,
            assessment_stage=assessment.stage,
            task_order_mode=TaskOrderMode.COUNTERBALANCED,
            task_order_group=assessment.task_order_group,
            task_order=tuple(order),
            task_position=assessment.current_position,
        )
        self._open_task_window(task, run, controlled=True)

    # ---------------------------------------------------------------- session
    def start_task(self, task: ExperimentType) -> None:
        if self.context.current_player is None or self.experiment_window is not None:
            return
        run: RunSetup = self.crosshair_combo.currentData() or RunSetup.baseline(self.context)
        if run.condition == Condition.CANDIDATE:
            parent_id = self.parent_session_id(task)
            if parent_id is None:
                self.banner.show_message(
                    "Run a baseline {task} session first; a candidate re-test is compared with it.",
                    Banner.Kind.WARNING, task=task_label(task))
                return
            run = RunSetup(
                run.crosshair, Condition.CANDIDATE, parent_id, run.recommendation_id
            )
        protocol = build_protocol(self.context.research)
        debug_order = tuple(str(value) for value in parse_task_order(protocol.debug_fixed_task_order))
        run = RunSetup(
            crosshair=run.crosshair,
            condition=run.condition,
            parent_session_id=run.parent_session_id,
            recommendation_id=run.recommendation_id,
            assessment_stage=AssessmentStage.COMBINED,
            task_order_mode=TaskOrderMode.DEBUG_FIXED,
            task_order_group="DEBUG",
            task_order=debug_order,
            task_position=debug_order.index(str(task)) + 1,
        )
        self._open_task_window(task, run, controlled=False)

    def _open_task_window(self, task: ExperimentType, run: RunSetup, controlled: bool) -> None:
        try:
            window = TASKS[task][2](self.context, run)
        except ValidationError as exc:
            self.banner.show_message(str(exc), Banner.Kind.ERROR)
            return
        window.finished.connect(self._on_experiment_finished)
        window.destroyed.connect(self._on_window_destroyed)
        self.experiment_window = window
        self._controlled_window = controlled
        self.controlled_button.setEnabled(False)
        screen = self.window().screen() if self.window() else None
        if screen is not None:
            window.setScreen(screen)
            window.setGeometry(screen.geometry())
        window.showFullScreen()
        window.activateWindow()
        window.setFocus()

    def _on_experiment_finished(self, session_id: int, status: str) -> None:
        self._last_session_id = session_id
        self.context.signals.data_changed.emit()
        if self._controlled_window and session_id and status == str(SessionStatus.COMPLETED):
            session = self.context.repository.get_session(session_id)
            if session is not None and session.assessment_id is not None:
                self.active_assessment = self.context.repository.complete_task_assessment_session(
                    session.assessment_id, session_id,
                )
        if session_id:
            trials = len(self.context.repository.list_trials(session_id))
            self.banner.show_message(
                "Session {session_id} {status}: {trials} trials saved.",
                Banner.Kind.SUCCESS if status == "completed" else Banner.Kind.WARNING,
                session_id=session_id, status=tr(status), trials=trials,
            )

    def _on_window_destroyed(self) -> None:
        controlled = self._controlled_window
        self.experiment_window = None
        self._controlled_window = False
        session_id, self._last_session_id = self._last_session_id, 0
        if controlled:
            if self.active_assessment is not None \
                    and self.active_assessment.status == AssessmentStatus.COMPLETED:
                self.banner.show_message(
                    "Controlled assessment complete. All assigned tasks were recorded.",
                    Banner.Kind.SUCCESS,
                )
            elif self.active_assessment is not None:
                template = ("Next practice: {task}"
                            if self.active_assessment.stage == AssessmentStage.PRACTICE
                            else "Next assessment: {task}")
                task = task_label(ExperimentType(self.active_assessment.current_task))
                self.banner.show_message(template, Banner.Kind.INFO, task=task)
            self._refresh_controlled_assessment()
            return
        if not session_id:
            return
        session = self.context.repository.get_session(session_id)
        if session is not None and session.condition == Condition.CANDIDATE:
            self.navigate_requested.emit(f"{PageId.COMPARISON}:{session_id}")
        else:
            self.navigate_requested.emit(f"{PageId.RESULTS}:{session_id}")
