-- Crosshair recommendation research database.
--
-- Design principles
--   * Raw measurement data (trials, trial_samples, trial_events) is append-only.
--     UPDATE and DELETE are blocked by triggers so raw data can never be
--     overwritten. Derived metrics (aim_results) can always be recomputed.
--   * Crosshair source data (crosshair_sources) is kept separate from
--     experimental measurement data.
--   * Every session records its condition (baseline / candidate), session
--     number, crosshair and environment so practice effects can be analysed.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Anonymous participants. No personally identifying information.
CREATE TABLE IF NOT EXISTS players (
    player_id              TEXT PRIMARY KEY,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    fps_experience         TEXT,
    aim_training_frequency TEXT,
    mouse_dpi              INTEGER CHECK (mouse_dpi IS NULL OR mouse_dpi > 0),
    sensitivity            REAL    CHECK (sensitivity IS NULL OR sensitivity > 0),
    edpi                   REAL    CHECK (edpi IS NULL OR edpi > 0),
    display_width          INTEGER CHECK (display_width IS NULL OR display_width > 0),
    display_height         INTEGER CHECK (display_height IS NULL OR display_height > 0),
    notes                  TEXT
);

-- Provenance of publicly collected / imported crosshair configurations.
CREATE TABLE IF NOT EXISTS crosshair_sources (
    source_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name   TEXT NOT NULL,
    source_url    TEXT,
    source_player TEXT,
    retrieved_at  TEXT NOT NULL,
    import_method TEXT NOT NULL CHECK (import_method IN ('scraper', 'csv', 'json', 'manual', 'builtin')),
    raw_payload   TEXT,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS crosshairs (
    crosshair_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    role              TEXT NOT NULL CHECK (role IN ('baseline', 'candidate', 'custom')),
    color             TEXT NOT NULL,
    size              REAL NOT NULL,
    thickness         REAL NOT NULL,
    gap               REAL NOT NULL,
    outline_enabled   INTEGER NOT NULL CHECK (outline_enabled IN (0, 1)),
    outline_thickness REAL NOT NULL,
    opacity           REAL NOT NULL CHECK (opacity >= 0 AND opacity <= 1),
    config_hash       TEXT NOT NULL,
    source_id         INTEGER REFERENCES crosshair_sources(source_id) ON DELETE RESTRICT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crosshairs_role   ON crosshairs(role);
CREATE INDEX IF NOT EXISTS idx_crosshairs_hash   ON crosshairs(config_hash);
CREATE INDEX IF NOT EXISTS idx_crosshairs_source ON crosshairs(source_id);

-- Snapshot of the measurement environment for a session.
CREATE TABLE IF NOT EXISTS environments (
    environment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at           TEXT NOT NULL,
    display_width        INTEGER,
    display_height       INTEGER,
    app_width            INTEGER,
    app_height           INTEGER,
    device_pixel_ratio   REAL,
    refresh_rate_hz      REAL,
    measured_fps         REAL,
    fov                  REAL,
    background_color     TEXT,
    background_condition TEXT,
    target_color         TEXT,
    target_size          REAL,
    target_speed         REAL,
    mouse_dpi            INTEGER,
    sensitivity          REAL,
    extra_json           TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id         TEXT    NOT NULL REFERENCES players(player_id) ON DELETE RESTRICT,
    started_at        TEXT    NOT NULL,
    ended_at          TEXT,
    experiment_type   TEXT    NOT NULL CHECK (experiment_type IN ('flick', 'tracking', 'switching')),
    condition         TEXT    NOT NULL CHECK (condition IN ('baseline', 'candidate')),
    session_number    INTEGER NOT NULL CHECK (session_number >= 1),
    status            TEXT    NOT NULL DEFAULT 'in_progress'
                              CHECK (status IN ('in_progress', 'completed', 'aborted')),
    crosshair_id      INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
    environment_id    INTEGER REFERENCES environments(environment_id) ON DELETE RESTRICT,
    random_seed       INTEGER,
    task_config_json  TEXT,
    parent_session_id INTEGER REFERENCES sessions(session_id) ON DELETE RESTRICT,
    recommendation_id INTEGER REFERENCES recommendations(recommendation_id) ON DELETE RESTRICT,
    app_version       TEXT,
    notes             TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_player    ON sessions(player_id);
CREATE INDEX IF NOT EXISTS idx_sessions_type      ON sessions(experiment_type, condition);
CREATE INDEX IF NOT EXISTS idx_sessions_crosshair ON sessions(crosshair_id);

-- One row per trial. Append-only raw data.
CREATE TABLE IF NOT EXISTS trials (
    trial_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           INTEGER NOT NULL REFERENCES sessions(session_id) ON DELETE RESTRICT,
    trial_number         INTEGER NOT NULL CHECK (trial_number >= 1),
    recorded_at          TEXT    NOT NULL,
    task_type            TEXT    NOT NULL CHECK (task_type IN ('flick', 'tracking', 'switching')),
    target_id            TEXT,
    previous_target_id   TEXT,
    target_x             REAL,
    target_y             REAL,
    target_size          REAL,
    target_distance      REAL,
    target_speed         REAL,
    initial_crosshair_x  REAL,
    initial_crosshair_y  REAL,
    result               TEXT    NOT NULL CHECK (result IN ('hit', 'miss', 'timeout', 'tracked', 'incomplete')),
    reaction_time_ms     REAL,
    movement_time_ms     REAL,
    completion_time_ms   REAL,
    error_distance       REAL,
    movement_distance    REAL,
    extra_json           TEXT,
    UNIQUE (session_id, trial_number)
);
CREATE INDEX IF NOT EXISTS idx_trials_session ON trials(session_id);

-- High-frequency cursor / target samples (trajectories). Append-only raw data.
CREATE TABLE IF NOT EXISTS trial_samples (
    sample_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_id   INTEGER NOT NULL REFERENCES trials(trial_id) ON DELETE RESTRICT,
    t_ms       REAL    NOT NULL,
    cursor_x   REAL    NOT NULL,
    cursor_y   REAL    NOT NULL,
    target_x   REAL,
    target_y   REAL,
    on_target  INTEGER CHECK (on_target IS NULL OR on_target IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_samples_trial ON trial_samples(trial_id, t_ms);

-- Discrete input events (clicks etc.). Append-only raw data.
CREATE TABLE IF NOT EXISTS trial_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    trial_id   INTEGER NOT NULL REFERENCES trials(trial_id) ON DELETE RESTRICT,
    t_ms       REAL    NOT NULL,
    event_type TEXT    NOT NULL,
    x          REAL,
    y          REAL,
    is_hit     INTEGER CHECK (is_hit IS NULL OR is_hit IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_events_trial ON trial_events(trial_id, t_ms);

-- Derived, recomputable session-level metrics.
CREATE TABLE IF NOT EXISTS aim_results (
    result_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    metric_name      TEXT    NOT NULL,
    metric_value     REAL,
    unit             TEXT,
    analysis_version TEXT    NOT NULL,
    computed_at      TEXT    NOT NULL,
    UNIQUE (session_id, metric_name, analysis_version)
);
CREATE INDEX IF NOT EXISTS idx_aim_results_session ON aim_results(session_id);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id          TEXT NOT NULL REFERENCES players(player_id) ON DELETE RESTRICT,
    created_at         TEXT NOT NULL,
    method             TEXT NOT NULL,
    method_version     TEXT NOT NULL,
    weights_json       TEXT NOT NULL,
    profile_json       TEXT NOT NULL,
    source_session_ids TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recommendations_player ON recommendations(player_id);

CREATE TABLE IF NOT EXISTS recommendation_candidates (
    candidate_row_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id    INTEGER NOT NULL REFERENCES recommendations(recommendation_id) ON DELETE CASCADE,
    crosshair_id         INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
    rank                 INTEGER NOT NULL,
    score                REAL    NOT NULL,
    component_scores_json TEXT   NOT NULL,
    explanation          TEXT    NOT NULL,
    selected_by_player   INTEGER NOT NULL DEFAULT 0 CHECK (selected_by_player IN (0, 1)),
    UNIQUE (recommendation_id, rank)
);

-- Raw-data immutability.
CREATE TRIGGER IF NOT EXISTS trials_no_update BEFORE UPDATE ON trials
BEGIN SELECT RAISE(ABORT, 'raw trial data is immutable'); END;
CREATE TRIGGER IF NOT EXISTS trials_no_delete BEFORE DELETE ON trials
BEGIN SELECT RAISE(ABORT, 'raw trial data is immutable'); END;
CREATE TRIGGER IF NOT EXISTS samples_no_update BEFORE UPDATE ON trial_samples
BEGIN SELECT RAISE(ABORT, 'raw trial data is immutable'); END;
CREATE TRIGGER IF NOT EXISTS samples_no_delete BEFORE DELETE ON trial_samples
BEGIN SELECT RAISE(ABORT, 'raw trial data is immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON trial_events
BEGIN SELECT RAISE(ABORT, 'raw trial data is immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON trial_events
BEGIN SELECT RAISE(ABORT, 'raw trial data is immutable'); END;
