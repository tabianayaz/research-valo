"""Full-screen Flick Aim window (procedure and timing: ``app.experiment.flick``)."""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from app.app_context import AppContext
from app.data.models import ExperimentType, Trial
from app.experiment.flick import (
    TIMING_DEFINITION,
    EventType,
    FlickConfig,
    FlickTarget,
    FlickTrialRecorder,
    generate_plan,
)
from app.ui.experiment_window import ExperimentWindow, RunSetup, State

__all__ = ["FlickExperimentWindow", "State"]


class FlickExperimentWindow(ExperimentWindow):
    experiment_type = ExperimentType.FLICK
    title = "Flick Aim"

    def __init__(self, context: AppContext, run: RunSetup | None = None, parent: QWidget | None = None) -> None:
        super().__init__(context, FlickConfig.from_dict(context.research.flick_task), run, parent)
        self.recorder: FlickTrialRecorder | None = None

    def build_plan(self, arena_w: int, arena_h: int, config: FlickConfig, seed: int) -> list[FlickTarget]:
        return generate_plan(config, arena_w, arena_h, seed)

    def timing_definition(self) -> dict[str, str]:
        return TIMING_DEFINITION

    def _current_target(self) -> FlickTarget:
        return self.plan[self.trial_index]

    def begin_trial(self, t: float, x: int, y: int) -> None:
        self.recorder = FlickTrialRecorder(self._current_target(), self.config)
        self.recorder.start_click(t, x, y)

    def on_onset(self, t0: float, x: int, y: int) -> None:
        self.recorder.target_shown(t0, x, y)
        self.timeout_timer.start(self.config.timeout_ms)

    def on_move(self, t: float, x: int, y: int) -> None:
        self.recorder.move(t, x, y)

    def on_click(self, t: float, x: int, y: int) -> None:
        if self.recorder.click(t, x, y):
            self._end_trial()

    def on_timeout(self, t: float, x: int, y: int) -> None:
        self.recorder.timeout(t, x, y)
        self._end_trial()

    def reset_trial(self) -> None:
        self.recorder = None

    def invalid_trial_fields(self) -> dict:
        target = self._current_target()
        return {"target_id": target.target_id, "target_x": target.x, "target_y": target.y,
                "target_size": self.config.target_diameter_px}

    def _end_trial(self) -> None:
        self.timeout_timer.stop()
        recorder = self.recorder
        target = recorder.target
        samples, events = recorder.raw()
        measures = recorder.measures()
        start_click = next(e for e in events if e.event_type == EventType.START_CLICK)
        stable = next((e for e in events if e.event_type == EventType.STABLE), start_click)
        trial = Trial(
            session_id=self.session.session_id,
            trial_number=self.next_trial_number(),
            task_type=ExperimentType.FLICK,
            result=measures.result,
            target_id=target.target_id,
            previous_target_id=self.plan[self.trial_index - 1].target_id if self.trial_index else None,
            target_x=target.x,
            target_y=target.y,
            target_size=self.config.target_diameter_px,
            target_distance=measures.target_distance,
            initial_crosshair_x=measures.initial_x,
            initial_crosshair_y=measures.initial_y,
            reaction_time_ms=measures.reaction_time_ms,
            movement_time_ms=measures.movement_time_ms,
            completion_time_ms=measures.completion_time_ms,
            error_distance=measures.error_distance,
            movement_distance=measures.movement_distance,
            **self.onset_quality(),
            extra={
                **self.common_extra(events, recorder.early_clicks),
                "planned_distance_px": target.planned_distance_px,
                "angle_deg": target.angle_deg,
                "foreperiod_ms_planned": target.foreperiod_ms,
                "foreperiod_ms_actual": -stable.t_ms,
                "stabilization_ms_actual": stable.t_ms - start_click.t_ms,
                "final_distance_px": measures.final_distance,
            },
        )
        self.recorder = None
        if self.save_trial(trial, samples, events):
            self.trial_done()

    def paint_task(self, painter: QPainter) -> None:
        target = self._current_target()
        self.draw_circle(painter, QPointF(target.x, target.y), self.config.target_diameter_px,
                         self.config.target_color)

    def intro_lines(self) -> list[str]:
        return [
            "Click the grey circle in the centre and hold the mouse still.",
            "A red target then appears. Move the crosshair onto it and click",
            "as quickly and accurately as possible. One click per trial.",
        ]
