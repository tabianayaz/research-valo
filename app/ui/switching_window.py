"""Full-screen Target Switching window (procedure: ``app.experiment.switching``)."""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from app.app_context import AppContext
from app.data.models import ExperimentType, TimingQuality, Trial, TrialStatus
from app.experiment.pointing import PointingRecorder
from app.experiment.switching import (
    TIMING_DEFINITION,
    SwitchingConfig,
    SwitchingTarget,
    SwitchingTrial,
    generate_switching_plan,
)
from app.i18n import tr
from app.ui.experiment_window import ExperimentWindow, RunSetup


class SwitchingExperimentWindow(ExperimentWindow):
    experiment_type = ExperimentType.SWITCHING
    title = "Target Switching"

    def __init__(self, context: AppContext, run: RunSetup | None = None, parent: QWidget | None = None) -> None:
        super().__init__(context, SwitchingConfig.from_dict(context.research.switching_task), run, parent)
        self.recorder: PointingRecorder | None = None
        self.segment = 0
        self.attempts: dict[int, int] = {}

    def build_plan(self, arena_w: int, arena_h: int, config: SwitchingConfig, seed: int) -> list[SwitchingTrial]:
        return generate_switching_plan(config, arena_w, arena_h, seed)

    def plan_for_storage(self, plan: list[SwitchingTrial]) -> list[dict]:
        return [
            {"index": t.index, "foreperiod_ms": t.foreperiod_ms, "targets": [vars(x) for x in t.targets]}
            for t in plan
        ]

    def on_phase_change(self) -> None:
        self.attempts = {}

    def timing_definition(self) -> dict[str, str]:
        return TIMING_DEFINITION

    def _trial(self) -> SwitchingTrial:
        return self.plan[self.trial_index]

    def _active_target(self) -> SwitchingTarget:
        return self._trial().targets[self.segment]

    def _new_recorder(self) -> PointingRecorder:
        target = self._active_target()
        return PointingRecorder(target.x, target.y, self.config.target_diameter_px,
                                self.config.movement_onset_threshold_px)

    def begin_trial(self, t: float, x: int, y: int) -> None:
        self.attempts[self.trial_index] = self.attempts.get(self.trial_index, 0) + 1
        self.segment = 0
        self.recorder = self._new_recorder()
        self.recorder.start_click(t, x, y)

    def on_onset(self, t0: float, x: int, y: int) -> None:
        self.recorder.target_shown(t0, x, y)
        self.timeout_timer.start(self.config.timeout_ms)

    def on_move(self, t: float, x: int, y: int) -> None:
        self.recorder.move(t, x, y)

    def on_click(self, t: float, x: int, y: int) -> None:
        if self.recorder.click(t, x, y):
            self._end_segment(t, x, y)

    def on_timeout(self, t: float, x: int, y: int) -> None:
        self.recorder.timeout(t, x, y)
        self._end_segment(t, x, y)

    def reset_trial(self) -> None:
        self.recorder = None
        self.segment = 0

    def invalid_trial_fields(self) -> dict:
        target = self._trial().targets[0]
        return {"target_id": target.target_id, "target_x": target.x, "target_y": target.y,
                "target_size": self.config.target_diameter_px}

    def _end_segment(self, t: float, x: int, y: int) -> None:
        self.timeout_timer.stop()
        recorder = self.recorder
        target = self._active_target()
        trial_plan = self._trial()
        samples, events = recorder.raw()
        measures = recorder.measures()
        previous = trial_plan.targets[self.segment - 1] if self.segment else None
        row = Trial(
            session_id=self.session.session_id,
            trial_number=self.next_trial_number(),
            task_type=ExperimentType.SWITCHING,
            result=measures.result,
            target_id=target.target_id,
            previous_target_id=previous.target_id if previous else None,
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
            **(self.onset_quality() if self.segment == 0 else
               {"trial_status": TrialStatus.VALID, "timing_quality": TimingQuality.PREVIOUS_CLICK}),
            extra={
                **self.common_extra(events, recorder.early_clicks),
                "switching_trial": trial_plan.index + 1,
                "sequence_index": self.segment,
                "is_switch": self.segment > 0,
                "attempt": self.attempts[self.trial_index],
                "planned_distance_px": target.planned_distance_px,
                "angle_deg": target.angle_deg,
                "foreperiod_ms_planned": trial_plan.foreperiod_ms if self.segment == 0 else None,
                "final_distance_px": measures.final_distance,
            },
        )
        if not self.save_trial(row, samples, events):
            return
        self.segment += 1
        if self.segment >= len(trial_plan.targets):
            self.recorder = None
            self.trial_done()
            return
        self._paints_in_trial = 0
        self.recorder = self._new_recorder()
        self.recorder.target_shown(t, x, y)
        self.timeout_timer.start(self.config.timeout_ms)
        self.update()

    def paint_task(self, painter: QPainter) -> None:
        for index, target in enumerate(self._trial().targets):
            if index < self.segment:
                continue
            color = self.config.target_color if index == self.segment else self.config.inactive_target_color
            self.draw_circle(painter, QPointF(target.x, target.y), self.config.target_diameter_px, color)

    def intro_lines(self) -> list[str]:
        return [
            "Click the grey circle in the centre and hold the mouse still.",
            tr("{count} targets then appear. Click the red one; the next target",
               count=self.config.targets_per_trial),
            "turns red immediately. One click per target, as quickly and accurately as possible.",
        ]
