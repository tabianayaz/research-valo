# Experiment protocol

How a session is run and recorded by the prototype. Every value is labelled:

- **CONFIRMED**: a property of the implementation that the software guarantees.
- **PLACEHOLDER**: a configurable value chosen only so that the software can be
  tested (`PILOT_PLACEHOLDER` in the configuration). It is not a research decision.
- **RESEARCH DECISION REQUIRED**: an open methodological choice.

All configurable values live in `app/config/research_parameters.json`. The
protocol is assembled in `app/experiment/protocol.py`, and the timing
definitions are in `app/experiment/timing.py`. Nothing in this document is a
scientific result.

## 1. Participant setup

- **CONFIRMED**: participants are identified only by an anonymous ID (for example `P-3368`).
- **CONFIRMED**: mouse DPI, in-game sensitivity and eDPI (DPI × sensitivity),
  FPS experience and aim-training frequency are stored with the participant.
  Mouse DPI and sensitivity are also copied into each session's environment record.
- **PLACEHOLDER**: the answer options for FPS experience and aim-training frequency.
- **RESEARCH DECISION REQUIRED**: whether eDPI must record the reference game
  (sensitivity scales differ between games). This is planned for a later phase.
- **RESEARCH DECISION REQUIRED**: the controlled environment (display, refresh rate,
  room, mouse) and the number of participants.

## 2. Practice procedure

- **CONFIRMED**: in a controlled three-task assessment, all enabled practice
  task blocks run first. After the final practice task, the experimental task
  sequence begins. Each task uses `protocol.practice_trial_count[task]` trials.
  The existing combined practice → experimental single-task window remains
  available only in clearly marked developer mode.
- **CONFIRMED**: practice trials use exactly the same interaction (start marker,
  stabilization, foreperiod, onset, response) and the same task parameters as
  experimental trials. Only the trial count and the seed differ
  (`protocol.practice_random_seed[task]`), so practice targets are not a
  preview of the experimental sequence.
- **CONFIRMED**: practice rows are stored with `trial_phase = practice`
  (raw samples and events are kept for audit). They are excluded from every
  metric, and therefore from the player profile, the recommendation and
  baseline/candidate comparisons. They are not counted in the participant's
  end-of-session summary, and practice trials that move before the target
  appears are not counted as invalid experimental trials.
- **CONFIRMED**: during practice, the corner label reads "Practice n / N"; during
  the experimental block it reads "Assessment n / N".
- **PLACEHOLDER**: practice enabled = true; practice trial counts: Flick 3, Tracking 1,
  Switching 1; the practice seeds.
- **RESEARCH DECISION REQUIRED**: the number of practice trials, whether practice
  is repeated before every session or only before the first, and whether
  practice should be required to reach a criterion.

## 3. Baseline procedure

- **CONFIRMED**: a baseline session uses the standard crosshair
  (`baseline_crosshair`). Changing the standard crosshair creates a new
  crosshair row; earlier sessions keep the row they used.
- **CONFIRMED**: every session stores an immutable snapshot of the crosshair it
  was run with (`sessions.crosshair_snapshot_json`: all crosshair fields plus
  `px_per_unit`).
- **CONFIRMED**: the player profile uses, per task, the latest completed baseline
  session. Candidate sessions, aborted sessions, practice trials and invalid
  trials are never used.
- **PLACEHOLDER**: the standard crosshair values (white, size 6, thickness 2,
  gap 3, outline 1, opacity 0.8; `baseline_confirmed: false`) and the profile
  source rule ("latest completed baseline").
- **RESEARCH DECISION REQUIRED**: the standard crosshair, the profile source rule,
  and the number of baseline sessions.

## 4. Experimental procedure

- **CONFIRMED**: three tasks: Flick Aim, Tracking and Target Switching. One
  session = one task, with one crosshair and one condition (baseline or candidate).
- **CONFIRMED**: a candidate (re-test) session links to the completed baseline
  session it is compared with. The comparison is descriptive only (no
  statistical test) and lists caveats, including a different protocol version.
- **CONFIRMED**: during a task the screen shows only the background, the stimuli,
  the start marker, the crosshair and a small trial counter. No scores, charts or
  recommendation information are shown during trials.
- **PLACEHOLDER**: all task parameters (`flick_task`, `tracking_task`,
  `switching_task`): trial counts, target size, target distances, tracking
  duration and path (which determines target speed), timeouts and foreperiod ranges.
- **RESEARCH DECISION REQUIRED**: the condition order (baseline / standard /
  candidate) and its counterbalancing, whether
  conditions use different but matched seeds, the number of sessions, and washout.

## 課題提示順序 (Task presentation order)

The three tasks are Flick Aim (F), Tracking (T) and Target Switching (S).

- **CONFIRMED**: the implementation contains all six permutations: FTS, FST,
  TFS, TSF, SFT and STF. They are defined in
  `app/experiment/task_order.py`; protocol snapshots store
  `task_order_method = counterbalanced`, all six
  `available_task_orders`, and
  `assignment_method = participant_sequence_modulo_6`.
- **CONFIRMED**: participants are assigned by their immutable 1-based creation
  sequence modulo six. The first six participants receive FTS, FST, TFS, TSF,
  SFT and STF; the rotation then repeats. The participant row stores the
  sequence, group and exact JSON order, so loading or resuming the same
  participant never makes a new assignment.
- **CONFIRMED**: each controlled assessment stores its assigned experimental
  order, practice order, current stage/task/position and completed practice and
  experimental tasks. Every linked session stores `task_order_group`,
  `task_order_json`, `task_position`, `assessment_stage` and
  `assessment_id`. Historical sessions remain NULL because their actual order
  cannot be inferred safely.
- **CONFIRMED**: controlled mode runs all practice tasks first and then all
  experimental tasks. By default, practice uses the assigned order
  (`practice_task_order_method = match_assigned`). A fixed practice order is a
  configurable alternative; this implementation does not claim either is
  optimal.
- **CONFIRMED**: if a task is aborted, its session remains aborted and its raw
  rows remain stored. The assessment stays at the same task. On recovery, an
  orphaned `in_progress` task session is marked aborted and a new session can
  resume the same persisted assessment ID, group, stage and position.
  Aborted sessions remain excluded from the baseline profile.
- **CONFIRMED**: participant-facing transitions say only “Next practice” or
  “Next assessment” plus the task name. The group is shown only when
  `debug_task_selection_enabled` is enabled. Fixed debug order is stored as
  `task_order_mode = debug_fixed` and never changes the participant assignment.
- **CONFIRMED**: Results, History and CSV/JSON exports retain the group, exact
  order and task position. Current metrics are unchanged; no correction for
  order effects is performed.
- **PLACEHOLDER**: participant-sequence modulo six is the current deterministic
  allocation strategy. It is an implementation choice, not evidence that this
  strategy is superior.
- **RESEARCH DECISION REQUIRED**: confirm the final allocation strategy,
  whether practice should match the experimental order, and how incomplete
  assessment runs should be handled in the study protocol.

## 5. Stabilization procedure

- **CONFIRMED**: after the start click, the cursor must stay within
  `stabilization_radius_px` of the centre and move less than
  `stabilization_movement_threshold_px` for `stabilization_duration_ms`.
  Leaving the region or moving restarts the period (`stabilization_reset` event).
  When the period is complete, a `stable` event stores the stable position and
  the foreperiod starts.
- **PLACEHOLDER**: radius 12 px, threshold 3 px, duration 300 ms (all tasks).
- **RESEARCH DECISION REQUIRED**: these three values, and whether Tracking and
  Switching should use the same rule as Flick (currently they do).

## 6. Target onset

- **CONFIRMED**: t = 0 is `perf_counter()` immediately after the first paint
  that contains the target.
- **CONFIRMED**: if no paint arrives within 50 ms, t = 0 comes from the fallback
  timer. The trial is then stored with `trial_status = timing_fallback` and
  `timing_quality = fallback`.
- **CONFIRMED**: Switching segments after the first start at the previous click
  (`timing_quality = previous_click`).
- **CONFIRMED (limitation)**: display and compositor latency after the paint is
  not measured.

## 7. Timing definitions

- **CONFIRMED**: the clock is `time.perf_counter()` in the Qt event handler. Times
  are stored in ms relative to t = 0 (negative values are before onset).
- **CONFIRMED**: movement onset is the first sample after t = 0 at least
  `movement_onset_threshold_px` from the stable pre-target position. Reaction
  time = t0 → movement onset. Movement time = movement onset → ending click.
  Completion time = t0 → ending click.
- **CONFIRMED**: the definition is versioned (`*-timing-2`) and stored with every
  session and trial.
- **PLACEHOLDER**: movement-onset threshold 3 px; the 100 ms window used for
  "moving at onset".
- **RESEARCH DECISION REQUIRED**: the reaction-time reference for Switching
  segments after the first.

## 8. Invalid trial rules

Analysis version `metrics-2` (`app/analysis/metrics.py`):

| Trial | Reaction time | Completion / switching time | Hit rate, click error | Tracking measures |
|---|---|---|---|---|
| valid | yes (unless moving at onset) | yes (hits) | yes | yes |
| timing_fallback | no | no | yes | no |
| invalid_pre_movement | no | no | no | no |
| practice | no | no | no | no |
| aborted session | shown in Results; never in the profile | | | |

- **CONFIRMED**: invalid and practice trials are counted
  (`invalid_pre_movement_count`, `practice_trials`) and listed in the Results
  table with a validity label. Nothing is discarded silently.
- **CONFIRMED**: an invalid trial is repeated (same planned trial).
- **CONFIRMED**: for Switching, only the latest attempt of a restarted
  experimental trial is used. Attempt numbering restarts for the experimental block.
- **PLACEHOLDER**: excluding "moving at onset" trials from reaction time.
- **RESEARCH DECISION REQUIRED**: a maximum number of repeats per planned trial
  (currently unlimited), and the exclusion criteria for whole sessions or participants.

## 9. Protocol versioning

- **CONFIRMED**: at session start the protocol is built from the current
  configuration. It covers practice settings, task order, all task parameters,
  background colour, crosshair unit scale, the standard crosshair and the
  timing version.
- **CONFIRMED**: `protocol_version = <label>+<12-hex hash of the snapshot>`.
  Any change to any of these values produces a new version automatically.
  The label (`protocol.label`, currently `pilot-placeholder`) is set by the researcher.
- **CONFIRMED**: each session stores `protocol_version` and the full snapshot
  (`sessions.protocol_snapshot_json`). It also keeps the actual task config and
  both plans (`task_config_json`: `plan`, `practice_plan`). A database trigger
  makes the snapshot columns write-once.
- **CONFIRMED**: historical sessions are analysed from their own stored values,
  not from the current configuration file.
- **CONFIRMED**: sessions recorded before protocol versioning have
  `protocol_version = NULL`. Their parameters remain available in `task_config_json`.
- **PLACEHOLDER**: `protocol.confirmed = false`.
- **RESEARCH DECISION REQUIRED**: the label scheme for the final protocol, and
  freezing the configuration before data collection.

## 10. Data retention

- **CONFIRMED**: trial, sample and event rows are append-only (database triggers
  block UPDATE and DELETE). Every trial is written as soon as it ends, so an
  abort or crash keeps completed trials. Invalid and practice trials are stored too.
- **CONFIRMED**: derived metrics (`aim_results`) are recomputable. Every analysis
  recomputes the metrics from raw data and reports any mismatch with the
  recorded values.
- **CONFIRMED**: before any schema migration of a database that contains
  research data, a backup is written to `data/backups/`. Migrations only add
  columns, indexes and triggers.
- **CONFIRMED**: exports (CSV/JSON) are written to new timestamped folders and
  never modify the database.
- **RESEARCH DECISION REQUIRED**: the retention period, storage location and access
  control for the research data (ethics approval).
