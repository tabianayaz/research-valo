"""Central timing and trial-validity definitions shared by all aim tasks.

Every session stores the definition it was recorded with
(``task_config["timing_definition"]``), so data stays interpretable if the
definitions change later. Thresholds are configuration values
(``research_parameters.json``) and are PILOT_PLACEHOLDER values, not
scientifically justified choices.

Clock
    ``time.perf_counter()`` (monotonic, high resolution), read in the Qt event
    handler that receives the input or paint. Stored times are milliseconds
    relative to target onset (t = 0); negative values are before onset.

Pre-target procedure (every trial that starts at the start marker)
    1. The participant clicks the central start marker (``start_click``).
    2. Stabilisation: the cursor must stay inside the stabilisation region
       (``stabilization_radius_px`` around the arena centre) and move less than
       ``stabilization_movement_threshold_px`` from its anchor position for
       ``stabilization_duration_ms``. Leaving the region or moving by the
       threshold restarts this period (``stabilization_reset``). When it is
       satisfied the ``stable`` event stores the stable cursor position.
    3. Foreperiod: a seeded random duration. If the cursor leaves the region or
       moves ``stabilization_movement_threshold_px`` or more from the stable
       position, the trial is invalidated (``pre_target_movement`` event,
       status ``invalid_pre_movement``); its raw data is saved, no target is
       shown, and the same planned trial is repeated after a new start click.
    4. Target onset (t = 0): ``perf_counter()`` immediately after the first
       paint that contains the target. If no paint arrives within
       ``ONSET_FALLBACK_MS`` the onset is taken from the fallback timer and the
       trial is marked ``timing_fallback``: it is excluded from reaction and
       completion time but kept for accuracy measures.

Measures
    movement onset   first sample after t = 0 whose distance from the stable
                     pre-target position is >= movement_onset_threshold_px
                     (trials recorded before stabilisation existed use the
                     position at t = 0)
    reaction time    target onset -> movement onset
    movement time    movement onset -> ending click
    completion time  target onset -> ending click (successful click for the
                     completion-time metrics)
    Display and compositor latency after the paint is not measured.
"""

from __future__ import annotations

ONSET_FALLBACK_MS = 50
TIMING_VERSION = "timing-2"

COMMON_TIMING_DEFINITION: dict[str, str] = {
    "timing_version": TIMING_VERSION,
    "clock": "time.perf_counter() in the Qt event handler, milliseconds relative to target onset",
    "stabilization": "after the start click the cursor must stay within stabilization_radius_px of the "
                     "centre and move < stabilization_movement_threshold_px for stabilization_duration_ms; "
                     "violations restart the period",
    "foreperiod_validity": "leaving the region or moving >= stabilization_movement_threshold_px from the stable "
                           "position during the foreperiod invalidates the trial (invalid_pre_movement); the "
                           "planned trial is repeated",
    "t0": "perf_counter() immediately after the first paint that contains the target",
    "timing_fallback": f"no paint within {ONSET_FALLBACK_MS} ms: t0 from the fallback timer, trial status "
                       "timing_fallback, excluded from reaction/completion time",
    "movement_onset": "first sample after t0 with distance >= movement_onset_threshold_px from the stable "
                      "pre-target position",
    "reaction_time": "t0 -> movement onset",
    "movement_time": "movement onset -> ending click",
    "completion_time": "t0 -> ending click",
}


def timing_definition(version: str, **task_specific: str) -> dict[str, str]:
    """A task's stored timing definition: the common part plus task-specific entries."""
    return {"version": version, **COMMON_TIMING_DEFINITION, **task_specific}
