"""Full-screen Tracking window (procedure and measures: ``app.experiment.tracking``)."""

from __future__ import annotations

import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from app.app_context import AppContext
from app.data.models import ExperimentType, Trial, TrialResult
from app.experiment.tracking import (
    TIMING_DEFINITION,
    TrackingConfig,
    TrackingPath,
    TrackingRecorder,
    generate_tracking_plan,
)
from app.i18n import tr
from app.ui.experiment_window import ExperimentWindow, RunSetup, State


class TrackingExperimentWindow(ExperimentWindow):
    experiment_type = ExperimentType.TRACKING
    title = "Tracking"

    def __init__(self, context: AppContext, run: RunSetup | None = None, parent: QWidget | None = None) -> None:
        super().__init__(context, TrackingConfig.from_dict(context.research.tracking_task), run, parent)
        self.recorder: TrackingRecorder | None = None
        self.on_target_ratios: list[float] = []
        self.sample_timer = QTimer(self, timerType=Qt.TimerType.PreciseTimer)
        self.sample_timer.setInterval(self.config.sample_interval_ms)
        self.sample_timer.timeout.connect(self._on_sample_tick)

    def build_plan(self, arena_w: int, arena_h: int, config: TrackingConfig, seed: int) -> list[TrackingPath]:
        return generate_tracking_plan(config, arena_w, arena_h, seed)

    def timing_definition(self) -> dict[str, str]:
        return TIMING_DEFINITION

    def environment_target_speed(self) -> float | None:
        if not self.experimental_plan:
            return None
        speeds = [p.mean_speed(self.config.trial_duration_ms) for p in self.experimental_plan]
        return sum(speeds) / len(speeds)

    def _current_path(self) -> TrackingPath:
        return self.plan[self.trial_index]

    def begin_trial(self, t: float, x: int, y: int) -> None:
        self.recorder = TrackingRecorder(self._current_path(), self.config)
        self.recorder.start_click(t, x, y)

    def on_onset(self, t0: float, x: int, y: int) -> None:
        self.recorder.target_shown(t0, x, y)
        self.timeout_timer.start(self.config.trial_duration_ms)
        self.sample_timer.start()

    def _on_sample_tick(self) -> None:
        if self.state != State.TARGET or self.recorder is None:
            return
        pos = self.cursor_or_center()
        self.recorder.sample(time.perf_counter(), pos.x(), pos.y())
        self.update()

    def on_move(self, t: float, x: int, y: int) -> None:
        self.recorder.sample(t, x, y)

    def on_click(self, t: float, x: int, y: int) -> None:
        self.recorder.click(t, x, y)

    def on_timeout(self, t: float, x: int, y: int) -> None:
        self.sample_timer.stop()
        recorder = self.recorder
        recorder.end(t, x, y)
        path = recorder.path
        samples, events = recorder.raw()
        measures = recorder.measures()
        trial = Trial(
            session_id=self.session.session_id,
            trial_number=self.next_trial_number(),
            task_type=ExperimentType.TRACKING,
            result=measures.result,
            target_id=path.target_id,
            previous_target_id=self.plan[self.trial_index - 1].target_id if self.trial_index else None,
            target_x=path.center_x,
            target_y=path.center_y,
            target_size=self.config.target_diameter_px,
            target_distance=None,
            target_speed=path.mean_speed(self.config.trial_duration_ms),
            initial_crosshair_x=measures.initial_x,
            initial_crosshair_y=measures.initial_y,
            reaction_time_ms=measures.reaction_time_ms,
            completion_time_ms=measures.duration_ms,
            error_distance=measures.mean_distance,
            movement_distance=measures.movement_distance,
            **self.onset_quality(),
            extra={
                **self.common_extra(events, recorder.early_clicks),
                "on_target_ratio": measures.on_target_ratio,
                "rms_distance_px": measures.rms_distance,
                "mean_distance_px": measures.mean_distance,
                "planned_duration_ms": self.config.trial_duration_ms,
                "foreperiod_ms_planned": path.foreperiod_ms,
                "sample_count": len([s for s in samples if s.t_ms >= 0]),
                "clicks": sum(1 for e in events if e.event_type == "click"),
            },
        )
        self.recorder = None
        if self.save_trial(trial, samples, events):
            if measures.result == TrialResult.TRACKED and measures.on_target_ratio is not None:
                self.on_target_ratios.append(measures.on_target_ratio)
            self.trial_done()

    def reset_trial(self) -> None:
        self.sample_timer.stop()
        self.recorder = None

    def invalid_trial_fields(self) -> dict:
        path = self._current_path()
        return {"target_id": path.target_id, "target_x": path.center_x, "target_y": path.center_y,
                "target_size": self.config.target_diameter_px}

    def paint_task(self, painter: QPainter) -> None:
        path = self._current_path()
        if self.state == State.TARGET and self.recorder is not None:
            x, y = path.position(self.recorder.elapsed_ms(time.perf_counter()))
        else:
            x, y = path.position(0.0)
        self.draw_circle(painter, QPointF(x, y), self.config.target_diameter_px, self.config.target_color)

    def intro_lines(self) -> list[str]:
        seconds = self.config.trial_duration_ms / 1000
        return [
            "Click the grey circle in the centre and hold the mouse still.",
            "A red target appears there and starts moving.",
            tr("Keep the crosshair on the target for {seconds} seconds. No clicking is needed.",
               seconds=format(seconds, "g")),
        ]

    def summary_lines(self) -> list[str]:
        if not self.on_target_ratios:
            return []
        mean = sum(self.on_target_ratios) / len(self.on_target_ratios)
        return [tr("time on target (mean of trials): {percent} %", percent=f"{mean * 100:.0f}")]
