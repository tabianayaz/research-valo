# Crosshair Recommendation Research Prototype

**FPS初級者の照準操作支援を目的としたプレイデータ分析に基づくクロスヘア推薦システムに関する研究**

A university graduation research prototype (HCI / FPS aiming). The system
measures a player's aiming performance, analyzes the measured characteristics,
presents several crosshair *candidates* for further testing, and compares
measured results after the player tries a candidate.

The goal is **not** to find a universally best crosshair. The goal is to help an
individual player find a crosshair that *may* suit their own measured aiming
characteristics:

```
measure -> analyze -> recommend candidates -> try -> re-measure -> compare
```

Target user: FPS beginners who can already perform basic mouse/aiming
operations but have limited experience choosing crosshair settings.

## Status

| Milestone | Content | Status |
|---|---|---|
| 1 | Project setup, PySide6 main window, navigation, SQLite initialization, data models | Done |
| 2 | CrosshairConfig, renderer, crosshair settings screen (+ VALORANT code importer, brought forward) | Done |
| 3 | Flick Aim task + raw trial logging (placeholder task parameters) | Done |
| 4 | Results + metric calculation | Done |
| 5 | Tracking task (placeholder task parameters; brought forward before 4) | Done |
| 6 | Target Switching task (placeholder task parameters; brought forward before 4) | Done |
| 7 | Player profile and analysis (placeholder source rule) | Done |
| 8 | Crosshair candidate database (built with Milestones 2 and 9) | Done |
| 9 | Web scraper / importer (brought forward: manual importer + Liquipedia adapter) | Done |
| 10 | Rule-based recommendation engine (placeholder weights and rules) | Done |
| 11 | Candidate re-test | Done |
| 12 | Comparison, history, export | Done |
| 13 | Testing, research documentation, polish | Planned |

## Technology

- Python 3.12+
- PySide6 (all UI, including the 2D aim canvas via `QPainter` / `QTimer`)
- SQLite (`sqlite3`)
- numpy / pandas / scipy / matplotlib for analysis and charts
- requests / BeautifulSoup4 / lxml for the optional crosshair source scraper
- pytest

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```powershell
python run.py
```

On first launch the database `data/app.db` is created automatically together
with `data/exports/`, `data/raw/` and `data/logs/`.

Environment overrides:

- `CROSSHAIR_RESEARCH_DATA_DIR` – alternative data directory
- `CROSSHAIR_RESEARCH_DB` – alternative database file

Keyboard: `Ctrl+1` … `Ctrl+9` switch between the navigation pages; `Tab`
moves focus (focused controls show an accent border).

## Test

```powershell
python -m pytest
```

UI smoke tests run headless (`QT_QPA_PLATFORM=offscreen` is set in
`tests/conftest.py`).

`python scripts/render_screens.py <out_dir>` renders every page to PNG using a
throwaway database (useful for thesis figures and visual checks).

## Architecture

```
app/
  main.py               entry point: settings -> logging -> database -> window
  app_context.py        shared state passed explicitly to pages (no globals)
  config/settings.py    paths and application constants
  data/
    schema.sql          relational schema (auto-applied, idempotent)
    database.py         connection management, schema initialization
    models.py           dataclasses mirroring rows + enums
    repository.py       the only module that issues SQL for domain objects
  ui/
    theme.py            dark theme stylesheet + palette
    components.py       BasePage, Card, Banner, MetricTile, PlaceholderPage, PageId
    main_window.py      sidebar navigation + stacked pages
    *_page.py           one module per screen
  utils/
    logging.py          structured key=value logging, uncaught-exception hook
    timing.py           perf_counter-based stopwatch, UTC timestamps
    validators.py       shared validation helpers
  crosshair/            CrosshairConfig, geometry, renderer, VALORANT mapping
  scraper/              code parser, importer, polite HTTP client, Liquipedia adapter
  experiment/           task plans, recorders and per-trial measures (flick, tracking, switching)
  analysis/             metrics (recomputed from raw data), profile, comparison, export
  recommendation/       rule-based candidate scoring (engine.py)
tests/
scripts/
```

Layers depend downward only: `ui -> (experiment, analysis, recommendation) -> data`.
The scraper writes into the crosshair source tables and never decides a
recommendation.

## Database structure

| Table | Kind | Purpose |
|---|---|---|
| `players` | metadata | Anonymous participants (no PII) |
| `crosshair_sources` | source data | Provenance of collected/imported crosshairs |
| `crosshairs` | config | Baseline, candidate and custom crosshair parameters |
| `environments` | snapshot | Display, FPS, background, target and mouse conditions per session |
| `sessions` | raw | One assessment run: type, condition (baseline/candidate), session number, seed, task config |
| `trials` | raw, append-only | One row per trial |
| `trial_samples` | raw, append-only | Cursor/target trajectory samples |
| `trial_events` | raw, append-only | Clicks and other discrete events |
| `aim_results` | derived | Session metrics; recomputable, versioned by `analysis_version` |
| `recommendations` | derived | Recommendation runs with weights, profile and method version |
| `recommendation_candidates` | derived | Ranked candidates with component scores and explanations |

Raw-data protection: SQLite triggers block every `UPDATE` and `DELETE` on
`trials`, `trial_samples` and `trial_events`. Aborted sessions are marked
`aborted`, never deleted.

Practice-effect support: every session stores `condition`
(`baseline`/`candidate`), a per-player `session_number`, the crosshair, the
environment snapshot, the random seed and an optional `parent_session_id`
linking a candidate re-test to the baseline it is compared with.

## Crosshair system

- **Research model** (`app/crosshair/config.py`): `CrosshairConfig` with exactly
  color, size, thickness, gap, outline (enabled + thickness) and opacity. The
  outline is black at the same opacity as the lines.
- **Geometry** (`app/crosshair/shape.py`): deterministic integer device-pixel
  rectangles; `units -> px = floor(units * px_per_unit + 0.5)`. Rules are in the
  module docstring and covered by tests.
- **Renderer** (`app/crosshair/renderer.py`): QPainter, antialiasing off, draws in
  physical pixels regardless of Windows display scaling.
- **Baseline**: `app/config/research_parameters.json` (the single place to change
  it). A changed baseline becomes a new `crosshairs` row; old sessions keep theirs.

### VALORANT share codes

`app/scraper/parsers.py` parses codes such as `0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0`
without losing information (all sections and unknown keys are preserved).
`app/crosshair/mapping.py` maps the primary crosshair into `CrosshairConfig` and
labels each code:

| Fidelity | Meaning |
|---|---|
| `exact` | every visible static element is represented |
| `approximate` | a config is produced; dropped/changed properties are listed |
| `not_representable` | e.g. dot-only or single-axis crosshairs; stored as source only |

Import via the UI (Crosshair → Crosshair database → Import) or:

```powershell
python scripts/import_valorant_codes.py codes.txt --source-name "..." [--source-url URL] [--player NAME]
python scripts/inspect_valorant_codes.py codes.txt   # dry run, no database writes
```

Each import line is `CODE`, `PLAYER, CODE` or `PLAYER, CODE, URL` (comma or
tab separated; `#` starts a comment). Per-line player/URL override the dialog
values. Duplicate codes from the same source and player are reported, not
re-stored.

Key meanings and defaults come from community documentation (Liquipedia
`Module:Crosshair`, valorant-spind.de), not an official Riot specification.
Preset colour RGB values are approximate.

### Optional source update (Liquipedia)

Crosshair → Crosshair database → **Update from Liquipedia…** collects
professional players' share codes from the
[Liquipedia VALORANT wiki](https://liquipedia.net/valorant/). It runs only when
started manually; the application never scrapes on launch and works fully
offline without it.

- Uses only the MediaWiki API (`list=embeddedin` + `prop=revisions` wikitext of
  `Template:CrosshairTable`), never HTML scraping or `action=parse`.
- Checks `robots.txt`, waits ≥ 2.5 s between requests, gzip, disk cache with a
  7-day TTL in `data/raw/scraper_cache/liquipedia/` (a full run is ~10 requests).
- Requires a contact e-mail or URL in the User-Agent, as Liquipedia's API terms
  require. It is stored locally in `data/scraper_settings.json`.
- Content is CC-BY-SA 3.0. Each record stores the page title, revision id and
  an `oldid` permalink for attribution; the date and reference on the wiki are
  kept in `raw_payload`.
- Pages using the older `Crosshair table` template (explicit parameters, no
  share code) and user-namespace pages are skipped and listed in the report.

Network fetching runs in a background thread and never touches the database;
importing happens afterwards through the same importer as manual input, so
source data stays separate from measurement data.

**tracker.gg is intentionally not supported**: its terms of service prohibit
automated collection and it blocks non-browser clients. Codes seen there can be
pasted into the manual importer with the player name and URL.

## Flick Aim (Milestone 3)

Assessment → Flick Aim → Start opens a full-screen window that shows only the
background, a start marker / target and the standard crosshair (the system
cursor is hidden; the crosshair is drawn at the mouse position).

Each trial: click the grey start marker in the centre → seeded random
foreperiod → red target appears (t = 0) → the first click ends the trial (hit
if the crosshair centre is within the target radius), or a timeout. Esc asks
to abort; completed trials are always kept and the session is marked
`aborted`.

Every trial is stored immediately with all cursor samples and events
(`start_click`, `early_click`, `target_onset`, `click`, `timeout`). Times are
milliseconds relative to t = 0. Exact definitions of t = 0, reaction time,
movement time, completion time, error distance and movement distance are in
the docstring of `app/experiment/flick.py` and are also stored in each
session's `task_config_json` (`timing_definition`). `compute_flick_measures`
recomputes every trial measure from the raw samples/events.

Task parameters (`flick_task` in `app/config/research_parameters.json`) are
**placeholders** (`confirmed: false`): 30 trials, 40 px targets at 150/300/450
px, 3000 ms timeout, 400–900 ms foreperiod, 3 px movement-onset threshold, fixed
seed. Sessions record this flag in their notes.

## Tracking (Milestone 5) and Target Switching (Milestone 6)

All three tasks share the same window (`app/ui/experiment_window.py`): start
marker → seeded foreperiod → stimulus onset (t = 0) → task → next trial;
Esc aborts; every trial row is stored immediately.

- **Tracking** (`app/experiment/tracking.py`): the target appears at the centre
  and follows a seeded sum-of-sines path for `trial_duration_ms`. Samples are
  taken on every mouse move and every `sample_interval_ms`; measures are
  time-weighted: on-target ratio, mean and RMS distance, reaction time,
  movement distance. Result is `tracked`; clicks are stored but not needed.
- **Target Switching** (`app/experiment/switching.py`): all targets of a trial
  are shown; the active one is red. One click per target; the next target
  becomes active at that click. One `trials` row per target, linked through
  `previous_target_id`; for switches the completion time is the switching time.
  Per-target measures are the same as Flick Aim (`app/experiment/pointing.py`).

Placeholders (`tracking_task`, `switching_task` in `research_parameters.json`,
`confirmed: false`): Tracking 6 × 6 s, 48 px target, amplitude 360/220 px;
Switching 10 trials × 3 targets, 40 px, first distance 150/300 px, switch
distance 200/350 px, 3000 ms timeout per target.

## Results, profile, recommendation, re-test, comparison (Milestones 4, 7, 10–12)

1. **Results** (`app/analysis/metrics.py`, analysis version `metrics-1`): every
   trial measure is recomputed from the stored samples and events, compared
   with the values stored at recording time (mismatches are shown), and
   aggregated into session metrics (medians for times; completion/switching
   times from hits only). Metrics are stored in `aim_results` as derived data.
   *Export CSV / JSON* writes trials, samples, events and session metadata to
   `data/exports/`.
2. **Profile** (`app/analysis/profile.py`): per task, the participant's initial
   *completed baseline* session. Standard, candidate, practice, familiarization
   and aborted sessions are never used. Profiles are per participant ID.
3. **Recommendation** (`app/recommendation/engine.py`): a transparent weighted
   score over four components (visibility = WCAG contrast against the
   background, centre precision, low occlusion, source fidelity). Rules in
   `research_parameters.json` → `recommendation` raise component weights when a
   profile metric crosses a threshold. Crosshairs identical to the baseline,
   and duplicates, are excluded. Each run is stored with its profile, weights,
   rule outcomes and ranked candidates. This is not a validated model.
4. **Re-test**: on Aim Assessment choose a candidate from the latest
   recommendation. The session is stored with condition `candidate`, the
   recommendation id, and `parent_session_id` = the latest completed baseline
   session of the same task. Task parameters are unchanged; since protocol-3
   the candidate condition uses its own seed, so the target sequence differs.
   In participant mode the controlled post-baseline run is the **crosshair
   evaluation** (Phase 5): the participant selects one candidate, then runs
   Candidate and Standard (baseline crosshair repeated) in the stored order
   CS or SC, each with a familiarization block. See 「クロスヘア条件の比較方法」
   in `docs/experiment_protocol.md`.
5. **Comparison** (`app/analysis/comparison.py`): candidate minus baseline for
   every metric, % difference for times and distances only, percentage points
   for ratios, with caveats (single sessions, order/practice effect,
   placeholders, moving at onset). No statistical test. *Export CSV* writes the
   table. For a crosshair evaluation the page also shows Baseline→Standard,
   Baseline→Candidate and Standard→Candidate. History lists all sessions
   (double-click opens them) and all recommendation runs.

## Timing conventions

- Durations use `time.perf_counter()` (monotonic, high resolution) in milliseconds.
- Wall-clock timestamps are ISO 8601 UTC and are used only to record *when*
  something happened.
- Exact start/stop events for reaction time, movement time and switching time
  are defined per task in Milestones 3, 5 and 6 and documented in
  `docs/experiment_protocol.md`.
- Common trial procedure (`app/experiment/timing.py`, timing version
  `*-timing-2`): start click → **stabilization** (cursor inside
  `stabilization_radius_px` and moving less than
  `stabilization_movement_threshold_px` for `stabilization_duration_ms`;
  movement restarts it, logged as `stabilization_reset`) → `stable` event →
  foreperiod → target onset (t = 0 after the first paint).
- Moving ≥ the threshold or leaving the region during the foreperiod
  **invalidates** the trial: the raw samples/events are stored with
  `trial_status = invalid_pre_movement` (result `incomplete`) and the same
  planned trial is repeated. Invalid trials are excluded from all metrics and
  counted (`invalid_pre_movement_count`).
- If no paint arrives within 50 ms, t0 comes from the fallback timer and the
  trial is stored with `trial_status = timing_fallback`,
  `timing_quality = fallback`. Such trials are excluded from time measures
  but kept for hit rate / click error.
- Analysis `metrics-2` applies per-measure validity
  (`valid_for_reaction_time`, `valid_for_completion_time`,
  `valid_for_accuracy`, `valid_for_tracking`), exported in `trials.csv`.
  Trials recorded before schema 3 have no stored status; it is derived from
  `extra.onset_from_paint`.

## Practice block and protocol versioning

Full procedure: `docs/experiment_protocol.md`.

- `protocol` in `research_parameters.json` holds `practice_enabled`,
  `practice_trial_count` and `practice_random_seed` per task (all
  PILOT_PLACEHOLDER). Controlled mode runs all practice task blocks first,
  then all experimental task blocks. Practice rows are stored
  (`trial_phase = practice`) but excluded from metrics, the profile, the
  recommendation and comparisons.
- Each session stores `protocol_version` (`<label>+<hash>`; any parameter
  change gives a new version), the full protocol snapshot, and a snapshot of
  the crosshair used. These are write-once (schema migration 4).
- Task order is counterbalanced across FTS, FST, TFS, TSF, SFT and STF.
  Participants are assigned in creation sequence modulo six and keep the
  stored assignment throughout the experiment. Assessment progress is
  persisted, so an aborted task resumes at the same stage, task and position.
  Sessions and exports retain group, exact order and position (schema
  migration 5). The allocation method remains a research decision.

## Research decisions still required

These choices affect research validity and are intentionally **not** decided
by the software. They need confirmation (e.g. with the supervisor):

1. **Player Setup categories.** FPS experience and aim-training frequency
   options in `app/ui/setup_page.py` are provisional placeholders.
2. **eDPI definition.** Implemented as DPI × in-game sensitivity. Sensitivity
   scales differ between games; decide whether to record the reference game.
3. **Standard (baseline) crosshair parameters.** Current values are a
   placeholder (VALORANT's default inner lines: white, size 6, thickness 2,
   gap 3, outline 1, opacity 0.8) with `baseline_confirmed: false`.
6. **Research crosshair model vs. VALORANT model.** The model lacks center dot,
   outer lines, separate vertical length and outline opacity, so 4 of the 16
   provided unique codes are not representable and 7 are approximate.
7. **Crosshair unit scale.** `px_per_unit = 1.0` (1 unit = 1 physical pixel).
   Whether sizes should scale with display resolution is undecided.
4. **Controlled environment.** Target size, target color, background color and
   window/fullscreen mode – constant across participants or not.
5. **Trial counts, timeouts, seeds** for each task, and whether all
   participants receive identical seeds (identical target sequences).
8. **Flick Aim procedure.** All `flick_task` values are placeholders. Also
   undecided: crosshair follows the mouse (current) vs. a fixed centre
   crosshair with a moving view; one click per trial (current) vs. click until
   hit; practice counts; distances in physical pixels regardless of display
   size; the same experimental seed for every participant (current).
   Tracking and Target Switching: all `tracking_task` / `switching_task` values,
   the path model (sum of sines), whether tracking should require holding the
   mouse button, and one click per switching target (current) vs. click until
   hit. Confirm the participant-sequence-modulo-six allocation strategy and
   whether practice should follow the assigned task order.
9. **Candidate source scope.** Liquipedia data are professional players'
   self-reported settings at a given date. Whether they form an appropriate
   candidate pool for beginners, and whether the older `Crosshair table`
   entries should be converted, is undecided.
10. **Stabilization and pre-target movement.** A stabilization period and
    foreperiod invalidation are implemented; radius 12 px, threshold 3 px and
    duration 300 ms are `PILOT_PLACEHOLDER` values. Undecided: these values,
    a maximum number of repeats per planned trial (currently unlimited),
    and whether trials still flagged `moving_at_onset` (sub-threshold
    movement) should be excluded from reaction time (currently excluded).
11. **Profile source rule.** Initial completed baseline session per task
    (placeholder). Alternatives: all baseline sessions, best-of, a fixed
    session number.
12. **Recommendation components, weights, normalisation and rules**
    (`recommendation`, `confirmed: false`). Every rule is a placeholder
    hypothesis; none is validated. Also undecided: top N, and whether source
    fidelity should influence the score at all.
13. **Re-test design.** Candidate and Standard sessions always follow the
    baseline (order effect); their order is counterbalanced (CS / SC,
    placeholder allocation) and each condition uses its own seed (placeholder
    values). Undecided: number of sessions per condition, washout / rest
    duration, familiarization length, and the allocation method. Evaluation
    sessions are compared with the initial baseline; individual debug re-tests
    with the latest completed baseline of the same task. Participants can also re-test their
    own custom crosshairs or any database crosshair; such sessions have no
    `recommendation_id`. Whether these are allowed in the study is undecided.

## Limitations (current milestone)

- Functional: the full measure → analyse → recommend → re-test → compare
  workflow, crosshair baseline/editor/database, VALORANT code import and the
  optional Liquipedia update.
- All task, recommendation and baseline parameters are placeholders.
- `docs/*.md` research documentation is Milestone 13.
- Movement/firing error and ADS/sniper crosshairs are stored but not rendered.
- No experimental results are included or implied.
