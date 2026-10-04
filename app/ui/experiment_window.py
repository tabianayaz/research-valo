"""Shared full-screen experiment window used by all aim tasks.

Shows only the background, the task's stimuli and the crosshair. The system
cursor is hidden; the crosshair is drawn at the mouse position (rendered
centre in device pixels). Every trial row is written to the database as soon
as it ends, so an abort or crash never loses completed trials.

Common procedure (implemented here): intro -> [start marker click ->
stabilization -> foreperiod -> stimulus onset (t = 0 after the first paint,
50 ms fallback) -> task-specific trial] x trial_count -> summary. Movement
during the foreperiod invalidates and repeats the trial. Definitions:
``app.experiment.timing``. Subclasses implement the task-specific hooks.
"""

from __future__ import annotations

import math
import platform
import time
from dataclasses import asdict, dataclass, replace
from enum import Enum, auto
from typing import Any

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QMessageBox, QWidget

from app import __version__
from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.crosshair.renderer import paint_shape
from app.data.models import (
    NON_ANALYSED_STAGES,
    AssessmentStage,
    Condition,
    CrosshairRecord,
    Environment,
    ExperimentType,
    Session,
    SessionStatus,
    TimingQuality,
    Trial,
    TrialPhase,
    TrialEvent,
    TrialResult,
    TrialSample,
    TrialStatus,
    TaskOrderMode,
)
from app.experiment.common import EventType
from app.experiment.conditions import seed_group_for
from app.experiment.protocol import ExperimentProtocol, build_protocol
from app.experiment.task_order import parse_task_order
from app.experiment.timing import ONSET_FALLBACK_MS
from app.i18n import tr, tr_message
from app.utils.logging import get_logger
from app.utils.validators import ValidationError

log = get_logger("ui.experiment")

TEXT_COLOR = "#D5DAE0"
FAINT_TEXT_COLOR = "#8A939C"


PRACTICE_COMPLETE_TEXT = "Practice complete. The experimental assessment will begin."


class State(Enum):
    INTRO = auto()
    TRANSITION = auto()  # between the practice block and the experimental block
    WAIT_START = auto()
    STABILIZING = auto()
    FOREPERIOD = auto()
    TARGET_PENDING = auto()
    TARGET = auto()
    DONE = auto()


@dataclass(frozen=True)
class RunSetup:
    """Crosshair and condition of one session.

    Baseline sessions use the standard crosshair. Candidate sessions (re-test)
    use a recommended candidate and link to the baseline session they are
    compared with (``parent_session_id``) and the recommendation run.
    Post-baseline condition sessions of an evaluation cycle (STANDARD /
    CANDIDATE) also carry the cycle's linking fields (``evaluation_id`` ...).
    """

    crosshair: CrosshairRecord
    condition: Condition = Condition.BASELINE
    parent_session_id: int | None = None
    recommendation_id: int | None = None
    assessment_id: int | None = None
    assessment_stage: AssessmentStage = AssessmentStage.COMBINED
    task_order_mode: TaskOrderMode = TaskOrderMode.INDIVIDUAL
    task_order_group: str | None = None
    task_order: tuple[str, ...] | None = None
    task_position: int | None = None
    evaluation_id: int | None = None
    condition_order_group: str | None = None
    condition_order: tuple[str, ...] | None = None
    condition_position: int | None = None
    initial_baseline_session_id: int | None = None
    selected_candidate_id: int | None = None
    show_condition_details: bool = False  # researcher/debug mode only

    @property
    def pre_block_stage(self) -> AssessmentStage:
        """Non-analysed block before the experimental trials: familiarization in evaluation cycles."""
        return AssessmentStage.FAMILIARIZATION if self.evaluation_id is not None else AssessmentStage.PRACTICE

    @property
    def participant_neutral(self) -> bool:
        """Evaluation runs never show the condition, its order or performance to the participant."""
        return self.evaluation_id is not None and not self.show_condition_details

    @classmethod
    def baseline(cls, context: AppContext) -> RunSetup:
        player = context.current_player
        return cls(
            context.baseline_crosshair,
            task_order_group=player.task_order_group if player else None,
            task_order=player.task_order if player else None,
        )


class ExperimentWindow(QWidget):
    finished = Signal(int, str)  # session_id (0 if never started), final status

    experiment_type: ExperimentType
    title: str

    def __init__(self, context: AppContext, config: Any, run: RunSetup | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.context = context
        self.config = config
        self.run = run or RunSetup.baseline(context)
        self.shape = CrosshairConfig.from_record(self.run.crosshair).to_shape()
        self.background = QColor(context.research.experiment_background_color)
        self.setWindowTitle(tr(self.title))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.state = State.INTRO
        self.session: Session | None = None
        self.protocol: ExperimentProtocol | None = None
        self.phase = TrialPhase.EXPERIMENTAL
        self.practice_plan: list[Any] = []
        self.experimental_plan: list[Any] = []
        self.plan: list[Any] = []  # plan of the current phase
        self.trial_index = 0
        self.rows_saved = 0
        self.results: list[TrialResult] = []
        self.cursor_px: QPoint | None = None
        self._trial_active = False
        self._paints_in_trial = 0
        self._onset_from_paint = True
        self._emitted = False

        self.invalid_trials = 0
        self._invalid_notice = False
        self._stable_anchor: tuple[int, int] | None = None
        self._stable_pos: tuple[int, int] | None = None
        self.recorder: Any = None

        self.stabilize_timer = QTimer(self, singleShot=True, timerType=Qt.TimerType.PreciseTimer)
        self.stabilize_timer.timeout.connect(self._on_stable)
        self.foreperiod_timer = QTimer(self, singleShot=True, timerType=Qt.TimerType.PreciseTimer)
        self.foreperiod_timer.timeout.connect(self._show_target)
        self.timeout_timer = QTimer(self, singleShot=True, timerType=Qt.TimerType.PreciseTimer)
        self.timeout_timer.timeout.connect(self._on_timeout_timer)

    # ------------------------------------------------------------ task hooks
    def build_plan(self, arena_w: int, arena_h: int, config: Any, seed: int) -> list[Any]:
        """Seeded plan for ``config.trial_count`` trials (used for practice and experimental blocks)."""
        raise NotImplementedError

    def on_phase_change(self) -> None:
        """Called when the experimental block starts after practice."""

    def timing_definition(self) -> dict[str, str]:
        raise NotImplementedError

    def begin_trial(self, t: float, x: int, y: int) -> None:
        """Start marker clicked: create the trial recorder."""
        raise NotImplementedError

    def on_onset(self, t0: float, x: int, y: int) -> None:
        """Stimulus is visible; t0 is the trial's t = 0."""
        raise NotImplementedError

    def on_move(self, t: float, x: int, y: int) -> None:
        raise NotImplementedError

    def on_click(self, t: float, x: int, y: int) -> None:
        """Left click during foreperiod or trial."""
        raise NotImplementedError

    def on_timeout(self, t: float, x: int, y: int) -> None:
        """``timeout_timer`` fired during the trial."""

    def paint_task(self, painter: QPainter) -> None:
        raise NotImplementedError

    def reset_trial(self) -> None:
        """Discard the unfinished trial (after a cancelled abort or once an invalid trial is saved)."""

    def invalid_trial_fields(self) -> dict[str, Any]:
        """Target fields of the planned trial, stored with an invalid (pre-movement) trial row."""
        return {}

    def intro_lines(self) -> list[str]:
        raise NotImplementedError

    def summary_lines(self) -> list[str]:
        hits = sum(1 for r in self.results if r == TrialResult.HIT)
        timeouts = sum(1 for r in self.results if r == TrialResult.TIMEOUT)
        return [tr("hits {hits}  ·  misses {misses}  ·  timeouts {timeouts}",
                   hits=hits, misses=len(self.results) - hits - timeouts, timeouts=timeouts)]

    def environment_target_speed(self) -> float | None:
        return None

    def plan_for_storage(self, plan: list[Any]) -> list[dict[str, Any]]:
        return [vars(item) for item in plan]

    def current_foreperiod_ms(self) -> int:
        return self.plan[self.trial_index].foreperiod_ms

    # --------------------------------------------------------------- geometry
    def _dpr(self) -> float:
        return self.devicePixelRatioF()

    def _arena_px(self) -> tuple[int, int]:
        dpr = self._dpr()
        return int(self.width() * dpr), int(self.height() * dpr)

    def _center_px(self) -> QPointF:
        w, h = self._arena_px()
        return QPointF(w / 2, h / 2)

    def _to_device(self, pos: QPointF) -> QPoint:
        dpr = self._dpr()
        return QPoint(round(pos.x() * dpr), round(pos.y() * dpr))

    def cursor_or_center(self) -> QPoint:
        return self.cursor_px if self.cursor_px is not None else self._center_px().toPoint()

    # ---------------------------------------------------------------- session
    def _start_session(self) -> bool:
        player = self.context.current_player
        if player is None:
            QMessageBox.warning(self, tr(self.title), tr("No participant selected."))
            return False
        arena_w, arena_h = self._arena_px()
        pre_stage = self.run.pre_block_stage
        try:
            self.protocol = build_protocol(self.context.research)
            task = str(self.experiment_type)
            experimental_seed = self.protocol.experimental_seed(
                str(self.run.condition), task, self.config.random_seed)
            self.experimental_plan = self.build_plan(arena_w, arena_h, self.config, experimental_seed)
            pre_count = self.protocol.pre_block_count(str(pre_stage), task)
            pre_seed = self.protocol.pre_block_seed(str(pre_stage), task)
            self.practice_plan = self.build_plan(
                arena_w, arena_h, replace(self.config, trial_count=pre_count), pre_seed,
            ) if pre_count else []
        except Exception as exc:  # noqa: BLE001 - shown to the operator
            QMessageBox.critical(self, tr(self.title), tr_message(str(exc)))
            return False
        stage = AssessmentStage(self.run.assessment_stage)
        if stage in NON_ANALYSED_STAGES:
            if not self.practice_plan:
                QMessageBox.critical(self, tr(self.title), tr("No practice trials are configured for this task."))
                return False
            self.phase = TrialPhase.PRACTICE
            self.plan = self.practice_plan
        elif stage == AssessmentStage.EXPERIMENTAL:
            self.phase = TrialPhase.EXPERIMENTAL
            self.plan = self.experimental_plan
        else:
            self.phase = TrialPhase.PRACTICE if self.practice_plan else TrialPhase.EXPERIMENTAL
            self.plan = self.practice_plan or self.experimental_plan

        task_order = tuple(self.run.task_order or player.task_order or ())
        if not task_order:
            task_order = tuple(str(task) for task in ExperimentType)
        task_order = tuple(str(task) for task in parse_task_order(task_order))
        task_position = self.run.task_position or task_order.index(str(self.experiment_type)) + 1
        task_order_group = self.run.task_order_group or player.task_order_group

        repo = self.context.repository
        screen = self.screen()
        environment = repo.add_environment(Environment(
            display_width=int(screen.geometry().width() * self._dpr()) if screen else None,
            display_height=int(screen.geometry().height() * self._dpr()) if screen else None,
            app_width=arena_w,
            app_height=arena_h,
            device_pixel_ratio=self._dpr(),
            refresh_rate_hz=screen.refreshRate() if screen else None,
            background_color=self.background.name(),
            background_condition="solid",
            target_color=self.config.target_color,
            target_size=self.config.target_diameter_px,
            target_speed=self.environment_target_speed(),
            mouse_dpi=player.mouse_dpi,
            sensitivity=player.sensitivity,
            extra={
                "window_mode": "fullscreen" if self.isFullScreen() else "windowed",
                "screen_name": screen.name() if screen else None,
                "platform": platform.platform(),
                "pyside_version": pyside_version,
            },
        ))
        self.session = repo.create_session(Session(
            player_id=player.player_id,
            experiment_type=self.experiment_type,
            condition=self.run.condition,
            session_number=repo.next_session_number(player.player_id),
            crosshair_id=self.run.crosshair.crosshair_id,
            parent_session_id=self.run.parent_session_id,
            recommendation_id=self.run.recommendation_id,
            environment_id=environment.environment_id,
            random_seed=pre_seed if stage in NON_ANALYSED_STAGES else experimental_seed,
            task_config={
                str(self.experiment_type): self.config.to_dict(),
                "arena_px": [arena_w, arena_h],
                "timing_definition": self.timing_definition(),
                "plan": self.plan_for_storage(self.experimental_plan),
                "practice_plan": self.plan_for_storage(self.practice_plan),
                "experimental_seed": experimental_seed,
                "pre_block_stage": str(pre_stage),
                "pre_block_seed": pre_seed,
                "assessment_stage": str(stage),
                "research_parameters": self.context.research.as_dict(),
            },
            app_version=__version__,
            notes=None if self.config.confirmed
            else f"Placeholder task parameters ({self.experiment_type}_task.confirmed = false).",
            protocol_version=self.protocol.version,
            protocol_snapshot=self.protocol.stored_snapshot(),
            crosshair_snapshot={**asdict(self.run.crosshair), "px_per_unit": self.context.research.px_per_unit},
            assessment_id=self.run.assessment_id,
            assessment_stage=stage,
            task_order_mode=self.run.task_order_mode,
            task_order_group=task_order_group,
            task_order=task_order,
            task_position=task_position,
            evaluation_id=self.run.evaluation_id,
            condition_order_group=self.run.condition_order_group,
            condition_order=self.run.condition_order,
            condition_position=self.run.condition_position,
            initial_baseline_session_id=self.run.initial_baseline_session_id,
            selected_candidate_id=self.run.selected_candidate_id,
            seed_group=seed_group_for(self.run.condition, str(stage) if stage in NON_ANALYSED_STAGES
                                      else None),
        ))
        log.info("experiment_started type=%s session_id=%s protocol=%s practice=%s trials=%s arena=%sx%s",
                 self.experiment_type, self.session.session_id, self.protocol.version, len(self.practice_plan),
                 len(self.experimental_plan), arena_w, arena_h)
        return True

    def _finish(self, status: SessionStatus) -> None:
        self.stabilize_timer.stop()
        self.foreperiod_timer.stop()
        self.timeout_timer.stop()
        self.reset_trial()
        self._trial_active = False
        if self.session is not None and self.state != State.DONE:
            try:
                self.context.repository.finish_session(self.session.session_id, status)
            except Exception:  # noqa: BLE001
                log.exception("finish_session_failed session_id=%s", self.session.session_id)
        self.state = State.DONE
        self.update()
        if not self._emitted:
            self._emitted = True
            self.finished.emit(self.session.session_id if self.session else 0, str(status))

    # ----------------------------------------------------------- trial helpers
    def next_trial_number(self) -> int:
        return self.rows_saved + 1

    def current_phase(self) -> TrialPhase:
        return self.phase

    def common_extra(self, events: list[TrialEvent], early_clicks: int) -> dict[str, Any]:
        start = next((e for e in events if e.event_type == EventType.START_CLICK), None)
        first_t = start.t_ms if start else events[0].t_ms
        duration_s = max((events[-1].t_ms - first_t) / 1000.0, 1e-9)
        return {
            "timing_definition": self.timing_definition()["version"],
            "early_clicks": early_clicks,
            "onset_from_paint": self._onset_from_paint,
            "paint_rate_hz": self._paints_in_trial / duration_s,
        }

    def save_trial(self, trial: Trial, samples: list[TrialSample], events: list[TrialEvent],
                   count_result: bool = True) -> bool:
        if trial.trial_phase is None:
            trial = replace(trial, trial_phase=self.current_phase())
        try:
            self.context.repository.add_trial(trial, samples, events)
        except Exception as exc:  # noqa: BLE001 - never continue silently after a failed write
            log.exception("trial_write_failed session_id=%s trial=%s",
                          self.session.session_id, trial.trial_number)
            QMessageBox.critical(self, tr(self.title),
                                 tr("Could not save trial: {error}\nThe session is aborted.", error=exc))
            self._finish(SessionStatus.ABORTED)
            return False
        self.rows_saved += 1
        if count_result and self.phase == TrialPhase.EXPERIMENTAL:
            self.results.append(TrialResult(trial.result))
        return True

    def trial_done(self) -> None:
        """Advance to the next start marker, from practice to the experimental block, or finish."""
        self.timeout_timer.stop()
        self._trial_active = False
        self.trial_index += 1
        if self.trial_index < len(self.plan):
            self.state = State.WAIT_START
        elif self.phase == TrialPhase.PRACTICE \
                and self.run.assessment_stage == AssessmentStage.COMBINED:
            self.phase = TrialPhase.EXPERIMENTAL
            self.plan = self.experimental_plan
            self.trial_index = 0
            self.on_phase_change()
            self.state = State.TRANSITION
            log.info("practice_completed type=%s session_id=%s", self.experiment_type, self.session.session_id)
        else:
            log.info("task_block_completed type=%s phase=%s session_id=%s",
                     self.experiment_type, self.phase, self.session.session_id)
            self._finish(SessionStatus.COMPLETED)
            return
        self.update()

    # ----------------------------------------------------------- trial flow
    # Procedure and definitions: app.experiment.timing.
    def _on_start_click(self, t: float) -> None:
        pos = self.cursor_or_center()
        self._paints_in_trial = 0
        self._trial_active = True
        self._invalid_notice = False
        self._stable_anchor = None
        self._stable_pos = None
        self.begin_trial(t, pos.x(), pos.y())
        self.state = State.STABILIZING
        self._check_stability(t, pos.x(), pos.y())
        self.update()

    def _in_stabilization_region(self, x: float, y: float) -> bool:
        center = self._center_px()
        return math.hypot(x - center.x(), y - center.y()) <= self.config.stabilization_radius_px

    def _check_stability(self, t: float, x: int, y: int) -> None:
        """Restart the stabilisation period whenever the cursor leaves the region or moves."""
        if not self._in_stabilization_region(x, y):
            if self._stable_anchor is not None:
                self.stabilize_timer.stop()
                self._stable_anchor = None
                self.record_event(t, EventType.STABILIZATION_RESET, x, y)
            return
        if self._stable_anchor is not None:
            ax, ay = self._stable_anchor
            if math.hypot(x - ax, y - ay) < self.config.stabilization_movement_threshold_px:
                return
            self.record_event(t, EventType.STABILIZATION_RESET, x, y)
        self._stable_anchor = (x, y)
        self.stabilize_timer.start(self.config.stabilization_duration_ms)

    def _on_stable(self) -> None:
        if self.state != State.STABILIZING or self._stable_anchor is None:
            return
        t = time.perf_counter()
        pos = self.cursor_or_center()
        self._stable_pos = (pos.x(), pos.y())
        self.record_event(t, EventType.STABLE, *self._stable_pos)
        self.state = State.FOREPERIOD
        self.foreperiod_timer.start(self.current_foreperiod_ms())
        self.update()

    def _foreperiod_violation(self, x: int, y: int) -> bool:
        sx, sy = self._stable_pos
        return (not self._in_stabilization_region(x, y)
                or math.hypot(x - sx, y - sy) >= self.config.stabilization_movement_threshold_px)

    def _invalidate_pre_movement(self, t: float, x: int, y: int) -> None:
        """Movement during the foreperiod: save the raw data as an invalid trial and repeat the planned trial."""
        self.foreperiod_timer.stop()
        self.record_event(t, EventType.PRE_TARGET_MOVEMENT, x, y)
        sx, sy = self._stable_pos
        samples, events = self.recorder.raw_without_onset(t)
        trial = Trial(
            session_id=self.session.session_id,
            trial_number=self.next_trial_number(),
            task_type=self.experiment_type,
            result=TrialResult.INCOMPLETE,
            trial_status=TrialStatus.INVALID_PRE_MOVEMENT,
            timing_quality=TimingQuality.NOT_APPLICABLE,
            **self.invalid_trial_fields(),
            extra={
                "timing_definition": self.timing_definition()["version"],
                "plan_index": self.trial_index,
                "invalid_reason": "left_region" if not self._in_stabilization_region(x, y) else "moved",
                "displacement_px": math.hypot(x - sx, y - sy),
                "time_reference": "t = 0 is the pre_target_movement event (no target was shown)",
            },
        )
        self.reset_trial()
        self._trial_active = False
        if self.save_trial(trial, samples, events, count_result=False):
            self.invalid_trials += self.phase == TrialPhase.EXPERIMENTAL
            self._invalid_notice = True
            self.state = State.WAIT_START
            log.info("trial_invalid_pre_movement session_id=%s plan_index=%s",
                     self.session.session_id, self.trial_index)
            self.update()

    def record_event(self, t: float, kind: str, x: float, y: float) -> None:
        if self.recorder is not None:
            self.recorder.record_event(t, kind, x, y)

    def onset_quality(self) -> dict[str, Any]:
        """Status/timing fields for a trial whose t0 came from the stimulus paint (or its fallback)."""
        if self._onset_from_paint:
            return {"trial_status": TrialStatus.VALID, "timing_quality": TimingQuality.PAINT}
        return {"trial_status": TrialStatus.TIMING_FALLBACK, "timing_quality": TimingQuality.FALLBACK}

    def _show_target(self) -> None:
        self.state = State.TARGET_PENDING
        self._onset_from_paint = True
        self.repaint()
        if self.state == State.TARGET_PENDING:
            QTimer.singleShot(ONSET_FALLBACK_MS, self._onset_fallback)

    def _onset_fallback(self) -> None:
        """Start the trial even if the window was not repainted (e.g. obscured); flagged in the trial."""
        if self.state == State.TARGET_PENDING:
            self._onset_from_paint = False
            log.warning("target_onset_without_paint trial=%s", self.trial_index + 1)
            self._on_target_painted()

    def _on_target_painted(self) -> None:
        t0 = time.perf_counter()
        pos = self.cursor_or_center()
        self.state = State.TARGET
        self.on_onset(t0, pos.x(), pos.y())

    def _on_timeout_timer(self) -> None:
        if self.state == State.TARGET:
            pos = self.cursor_or_center()
            self.on_timeout(time.perf_counter(), pos.x(), pos.y())

    # ----------------------------------------------------------------- events
    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        t = time.perf_counter()
        self.cursor_px = self._to_device(event.position())
        x, y = self.cursor_px.x(), self.cursor_px.y()
        if self._trial_active:
            self.on_move(t, x, y)
            if self.state == State.STABILIZING:
                self._check_stability(t, x, y)
            elif self.state == State.FOREPERIOD and self._foreperiod_violation(x, y):
                self._invalidate_pre_movement(t, x, y)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            return
        t = time.perf_counter()
        self.cursor_px = self._to_device(event.position())
        x, y = self.cursor_px.x(), self.cursor_px.y()
        if self.state == State.WAIT_START:
            center = self._center_px()
            if (x - center.x()) ** 2 + (y - center.y()) ** 2 <= (self.config.start_marker_diameter_px / 2) ** 2:
                self._on_start_click(t)
        elif self.state in (State.STABILIZING, State.FOREPERIOD, State.TARGET_PENDING, State.TARGET):
            self.on_click(t, x, y)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        key = event.key()
        if self.state == State.INTRO:
            if key == Qt.Key.Key_Space and self._start_session():
                self.state = State.WAIT_START
                self.update()
            elif key == Qt.Key.Key_Escape:
                self._finish(SessionStatus.ABORTED)
                self.close()
        elif self.state == State.TRANSITION and key == Qt.Key.Key_Space:
            self.state = State.WAIT_START
            self.update()
        elif self.state == State.DONE:
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                self.close()
        elif key == Qt.Key.Key_Escape:
            self._confirm_abort()

    def _confirm_abort(self) -> None:
        self.stabilize_timer.stop()
        self.foreperiod_timer.stop()
        self.timeout_timer.stop()
        self.unsetCursor()
        answer = QMessageBox.question(
            self, tr("Abort session"),
            tr("Abort this session? Completed trials stay saved and the session is marked as aborted."),
        )
        self.setCursor(Qt.CursorShape.BlankCursor)
        if answer == QMessageBox.StandardButton.Yes:
            self._finish(SessionStatus.ABORTED)
        else:
            self.reset_trial()
            self._trial_active = False
            self.state = State.WAIT_START
            self.update()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.state != State.DONE:
            self._finish(SessionStatus.ABORTED)
        super().closeEvent(event)

    # --------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.background)

        if self.state == State.INTRO:
            self._draw_text(painter, "\n".join(self._intro_text()))
        elif self.state == State.TRANSITION:
            self._draw_text(painter, "\n".join([
                tr(PRACTICE_COMPLETE_TEXT), "", tr("Experimental Assessment"),
                tr("{count} trials", count=len(self.experimental_plan)), "", tr("Press Space to begin"),
            ]))
        elif self.state == State.DONE:
            self._draw_text(painter, self._done_text())
        elif self.state in (State.WAIT_START, State.STABILIZING):
            self.draw_circle(painter, self._center_px(), self.config.start_marker_diameter_px,
                             self.config.start_marker_color)
            painter.setPen(QColor(FAINT_TEXT_COLOR))
            painter.setFont(self._text_font(10))
            if self.phase != TrialPhase.PRACTICE:
                block = tr("Assessment")
            elif self.run.pre_block_stage == AssessmentStage.FAMILIARIZATION:
                block = tr("Familiarization")
            else:
                block = tr("Practice")
            painter.drawText(16, 26, f"{block}  {self.trial_index + 1} / {len(self.plan)}")
            notice = self._instruction()
            if notice:
                painter.setPen(QColor(TEXT_COLOR))
                painter.setFont(self._text_font(12))
                area = self.rect().adjusted(0, self.height() // 2 + 40, 0, 0)
                painter.drawText(area, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, notice)
        elif self.state in (State.TARGET_PENDING, State.TARGET):
            self.paint_task(painter)

        if self.cursor_px is not None and self.state not in (State.INTRO, State.DONE):
            paint_shape(painter, self.shape, self.cursor_px, self.context.research.px_per_unit, self._dpr())
        painter.end()

        if self._trial_active:
            self._paints_in_trial += 1
        if self.state == State.TARGET_PENDING:
            self._on_target_painted()

    def _instruction(self) -> str:
        if self.state == State.STABILIZING and self._stable_anchor is None:
            return tr("Return to the centre and hold still")
        if self.state == State.WAIT_START and self._invalid_notice:
            return tr("The mouse moved before the target appeared. This trial will be repeated.\n"
                      "Click the centre and hold still until the target appears.")
        return ""

    def draw_circle(self, painter: QPainter, center_px: QPointF, diameter_px: float, color: str) -> None:
        dpr = self._dpr()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        radius = diameter_px / 2 / dpr
        painter.drawEllipse(QPointF(center_px.x() / dpr, center_px.y() / dpr), radius, radius)
        painter.restore()

    def _text_font(self, point_size: int) -> QFont:
        """Application font (keeps its Japanese-capable fallback families) at ``point_size``."""
        font = QFont(self.font())
        font.setPointSize(point_size)
        return font

    def _draw_text(self, painter: QPainter, text: str) -> None:
        painter.setPen(QColor(TEXT_COLOR))
        painter.setFont(self._text_font(14))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

    def _intro_text(self) -> list[str]:
        pre_stage = self.run.pre_block_stage
        try:
            practice = build_protocol(self.context.research).pre_block_count(
                str(pre_stage), str(self.experiment_type))
        except ValidationError:
            practice = 0
        stage = AssessmentStage(self.run.assessment_stage)
        if stage == AssessmentStage.FAMILIARIZATION:
            block = [tr("Familiarization: {count} trials (not analysed)", count=practice)]
        elif stage == AssessmentStage.PRACTICE:
            block = [tr("Practice: {count} trials (not analysed)", count=practice)]
        elif stage == AssessmentStage.EXPERIMENTAL:
            block = [tr("Experimental Assessment: {count} trials", count=self.config.trial_count)]
        elif practice:
            block = [tr("Practice: {count} trials (not analysed), then", count=practice),
                     tr("Experimental Assessment: {count} trials", count=self.config.trial_count)]
        else:
            block = [tr("Experimental Assessment: {count} trials", count=self.config.trial_count)]
        lines = [tr(self.title), "", *(tr(line) for line in self.intro_lines()), "", *block, tr("Esc aborts")]
        if self.run.evaluation_id is not None:
            lines += ["", tr("Crosshair evaluation — part {position} of 2", position=self.run.condition_position)]
            if self.run.show_condition_details:
                lines += [tr("Researcher view: condition {condition}, order {group}, crosshair {name}",
                             condition=str(self.run.condition), group=self.run.condition_order_group,
                             name=self.run.crosshair.name)]
        elif self.run.condition == Condition.CANDIDATE:
            lines += ["", tr("Crosshair: candidate ({name})", name=self.run.crosshair.name)]
        lines += ["", tr("Press Space to begin")]
        if not self.config.confirmed:
            lines += ["", tr("(Task parameters are placeholders and not yet confirmed)")]
        return lines

    def _done_text(self) -> str:
        if self.run.assessment_stage in NON_ANALYSED_STAGES \
                and self.trial_index >= len(self.plan):
            template = ("Familiarization complete: {count} trials saved for audit (not analysed)"
                        if self.run.assessment_stage == AssessmentStage.FAMILIARIZATION
                        else "Practice complete: {count} trials saved for audit (not analysed)")
            return "\n".join([tr(template, count=len(self.plan)), "", tr("Press Space to continue")])
        if not self.results:
            return tr("Session ended. No experimental trials were recorded.\n\nPress Space to return")
        complete = self.phase == TrialPhase.EXPERIMENTAL and self.trial_index >= len(self.plan)
        invalid = (tr("  ·  {count} invalid (moved before the target) repeated", count=self.invalid_trials)
                   if self.invalid_trials else "")
        headline = (tr("Session complete: {count} trials saved{invalid}", count=len(self.results), invalid=invalid)
                    if complete else
                    tr("Session aborted: {count} trials saved{invalid}", count=len(self.results), invalid=invalid))
        return "\n".join([
            headline,
            *([] if self.run.participant_neutral else self.summary_lines()),
            "",
            tr("Press Space to return"),
        ])
