"""SQLite connection management and automatic schema initialization."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.utils.logging import get_logger

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# schema.sql is version 1. Later changes are applied as ordered migrations so
# existing research databases are upgraded in place without losing data.
MIGRATIONS: dict[int, str] = {
    2: """
    ALTER TABLE crosshair_sources ADD COLUMN source_format TEXT;
    ALTER TABLE crosshair_sources ADD COLUMN source_code TEXT;
    ALTER TABLE crosshairs ADD COLUMN fidelity TEXT
        CHECK (fidelity IS NULL OR fidelity IN ('exact', 'approximate'));
    CREATE INDEX IF NOT EXISTS idx_sources_code ON crosshair_sources(source_format, source_code);
    """,
    # Trial validity (Phase 2). Columns are nullable: rows recorded before this
    # migration keep NULL and their validity is derived during analysis.
    3: """
    ALTER TABLE trials ADD COLUMN trial_status TEXT
        CHECK (trial_status IS NULL OR trial_status IN ('valid', 'invalid_pre_movement', 'timing_fallback'));
    ALTER TABLE trials ADD COLUMN timing_quality TEXT
        CHECK (timing_quality IS NULL OR timing_quality IN ('paint', 'fallback', 'previous_click', 'not_applicable'));
    ALTER TABLE trials ADD COLUMN trial_phase TEXT
        CHECK (trial_phase IS NULL OR trial_phase IN ('practice', 'experimental'));
    """,
    # Protocol versioning and crosshair snapshot (Phase 3). NULL for sessions
    # recorded earlier (their task_config_json still holds the parameters).
    # Once written, the snapshot columns cannot be changed.
    4: """
    ALTER TABLE sessions ADD COLUMN protocol_version TEXT;
    ALTER TABLE sessions ADD COLUMN protocol_snapshot_json TEXT;
    ALTER TABLE sessions ADD COLUMN crosshair_snapshot_json TEXT;
    CREATE INDEX IF NOT EXISTS idx_sessions_protocol ON sessions(protocol_version);
    CREATE TRIGGER IF NOT EXISTS sessions_snapshot_immutable
        BEFORE UPDATE OF protocol_version, protocol_snapshot_json, crosshair_snapshot_json ON sessions
        WHEN OLD.protocol_version IS NOT NULL OR OLD.protocol_snapshot_json IS NOT NULL
             OR OLD.crosshair_snapshot_json IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'session protocol/crosshair snapshots are immutable'); END;
    """,
    # Deterministic task-order assignment and resumable controlled assessments
    # (Phase 4). Existing sessions remain NULL because their actual task
    # position cannot be inferred safely from historical rows.
    5: """
    ALTER TABLE players ADD COLUMN task_order_sequence INTEGER;
    ALTER TABLE players ADD COLUMN task_order_group TEXT
        CHECK (task_order_group IS NULL OR task_order_group IN ('FTS','FST','TFS','TSF','SFT','STF'));
    ALTER TABLE players ADD COLUMN task_order_json TEXT;

    WITH ranked AS (
        SELECT player_id, ROW_NUMBER() OVER (ORDER BY created_at, player_id) AS sequence
        FROM players
    )
    UPDATE players
       SET task_order_sequence = (SELECT sequence FROM ranked WHERE ranked.player_id = players.player_id);
    UPDATE players
       SET task_order_group = CASE ((task_order_sequence - 1) % 6)
           WHEN 0 THEN 'FTS' WHEN 1 THEN 'FST' WHEN 2 THEN 'TFS'
           WHEN 3 THEN 'TSF' WHEN 4 THEN 'SFT' ELSE 'STF' END;
    UPDATE players
       SET task_order_json = CASE task_order_group
           WHEN 'FTS' THEN '["flick","tracking","switching"]'
           WHEN 'FST' THEN '["flick","switching","tracking"]'
           WHEN 'TFS' THEN '["tracking","flick","switching"]'
           WHEN 'TSF' THEN '["tracking","switching","flick"]'
           WHEN 'SFT' THEN '["switching","flick","tracking"]'
           ELSE '["switching","tracking","flick"]' END;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_players_task_order_sequence
        ON players(task_order_sequence);
    CREATE INDEX IF NOT EXISTS idx_players_task_order_group
        ON players(task_order_group);
    CREATE TRIGGER IF NOT EXISTS players_task_order_immutable
        BEFORE UPDATE OF task_order_sequence, task_order_group, task_order_json ON players
        WHEN OLD.task_order_group IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'participant task-order assignment is immutable'); END;

    CREATE TABLE IF NOT EXISTS task_assessments (
        assessment_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id              TEXT NOT NULL REFERENCES players(player_id) ON DELETE RESTRICT,
        started_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL,
        condition              TEXT NOT NULL,
        crosshair_id           INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
        recommendation_id      INTEGER REFERENCES recommendations(recommendation_id) ON DELETE RESTRICT,
        task_order_group       TEXT NOT NULL
                               CHECK (task_order_group IN ('FTS','FST','TFS','TSF','SFT','STF')),
        task_order_json        TEXT NOT NULL,
        practice_order_json    TEXT NOT NULL,
        stage                  TEXT NOT NULL CHECK (stage IN ('practice','experimental')),
        current_position       INTEGER NOT NULL CHECK (current_position BETWEEN 1 AND 3),
        current_task           TEXT CHECK (current_task IS NULL OR current_task IN ('flick','tracking','switching')),
        completed_tasks_json   TEXT NOT NULL,
        status                 TEXT NOT NULL CHECK (status IN ('in_progress','completed')),
        protocol_version       TEXT,
        protocol_snapshot_json TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_task_assessments_player
        ON task_assessments(player_id, status);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_task_assessment
        ON task_assessments(player_id) WHERE status = 'in_progress';
    CREATE TRIGGER IF NOT EXISTS task_assessment_assignment_immutable
        BEFORE UPDATE OF player_id, condition, crosshair_id, recommendation_id,
                         task_order_group, task_order_json, practice_order_json,
                         protocol_version, protocol_snapshot_json
        ON task_assessments
        BEGIN SELECT RAISE(ABORT, 'task-assessment assignment is immutable'); END;

    ALTER TABLE sessions ADD COLUMN assessment_id INTEGER
        REFERENCES task_assessments(assessment_id) ON DELETE RESTRICT;
    ALTER TABLE sessions ADD COLUMN assessment_stage TEXT
        CHECK (assessment_stage IS NULL OR assessment_stage IN ('practice','experimental','combined'));
    ALTER TABLE sessions ADD COLUMN task_order_mode TEXT
        CHECK (task_order_mode IS NULL OR task_order_mode IN ('counterbalanced','debug_fixed','individual'));
    ALTER TABLE sessions ADD COLUMN task_order_group TEXT
        CHECK (task_order_group IS NULL OR task_order_group IN ('FTS','FST','TFS','TSF','SFT','STF','DEBUG'));
    ALTER TABLE sessions ADD COLUMN task_order_json TEXT;
    ALTER TABLE sessions ADD COLUMN task_position INTEGER
        CHECK (task_position IS NULL OR task_position BETWEEN 1 AND 3);
    CREATE INDEX IF NOT EXISTS idx_sessions_assessment ON sessions(assessment_id, task_position);
    CREATE INDEX IF NOT EXISTS idx_sessions_task_order ON sessions(task_order_group, task_position);
    CREATE TRIGGER IF NOT EXISTS sessions_task_order_immutable
        BEFORE UPDATE OF assessment_id, assessment_stage, task_order_mode,
                         task_order_group, task_order_json, task_position ON sessions
        WHEN OLD.task_order_group IS NOT NULL OR OLD.assessment_id IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'session task-order metadata is immutable'); END;
    """,
    # Standard / Candidate condition counterbalancing (Phase 5).
    # SQLite cannot alter a CHECK constraint, so allowing condition 'standard'
    # and stage 'familiarization' rebuilds `sessions` and `task_assessments`
    # (copy -> drop -> rename, SQLite's documented procedure). Raw trial,
    # sample and event tables are not touched. Every existing row is copied
    # unchanged; new columns stay NULL for historical rows because their
    # condition-order metadata cannot be inferred safely. The runner checks
    # row counts and foreign keys before committing (see initialize_schema).
    6: """
    ALTER TABLE players ADD COLUMN condition_order_group TEXT
        CHECK (condition_order_group IS NULL OR condition_order_group IN ('CS','SC'));
    ALTER TABLE players ADD COLUMN condition_order_json TEXT;
    ALTER TABLE players ADD COLUMN condition_assignment_method TEXT;
    CREATE TRIGGER IF NOT EXISTS players_condition_order_immutable
        BEFORE UPDATE OF condition_order_group, condition_order_json, condition_assignment_method ON players
        WHEN OLD.condition_order_group IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'participant condition-order assignment is immutable'); END;

    CREATE TABLE IF NOT EXISTS condition_evaluations (
        evaluation_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id                        TEXT NOT NULL REFERENCES players(player_id) ON DELETE RESTRICT,
        created_at                       TEXT NOT NULL,
        updated_at                       TEXT NOT NULL,
        recommendation_id                INTEGER NOT NULL UNIQUE
                                         REFERENCES recommendations(recommendation_id) ON DELETE RESTRICT,
        selected_candidate_id            INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
        standard_crosshair_id            INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
        standard_crosshair_snapshot_json TEXT NOT NULL,
        initial_baseline_sessions_json   TEXT NOT NULL,
        condition_order_group            TEXT NOT NULL CHECK (condition_order_group IN ('CS','SC')),
        condition_order_json             TEXT NOT NULL,
        condition_assignment_method      TEXT NOT NULL,
        current_position                 INTEGER NOT NULL CHECK (current_position BETWEEN 1 AND 2),
        status                           TEXT NOT NULL CHECK (status IN ('in_progress','completed')),
        protocol_version                 TEXT,
        protocol_snapshot_json           TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_condition_evaluations_player ON condition_evaluations(player_id, status);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_condition_evaluation
        ON condition_evaluations(player_id) WHERE status = 'in_progress';
    CREATE TRIGGER IF NOT EXISTS condition_evaluation_assignment_immutable
        BEFORE UPDATE OF player_id, recommendation_id, selected_candidate_id, standard_crosshair_id,
                         standard_crosshair_snapshot_json, initial_baseline_sessions_json,
                         condition_order_group, condition_order_json, condition_assignment_method,
                         protocol_version, protocol_snapshot_json
        ON condition_evaluations
        BEGIN SELECT RAISE(ABORT, 'condition-evaluation assignment is immutable'); END;

    CREATE TEMP TABLE _phase5_sequence AS
        SELECT name, seq FROM sqlite_sequence WHERE name IN ('sessions', 'task_assessments');

    CREATE TABLE new_task_assessments (
        assessment_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id              TEXT NOT NULL REFERENCES players(player_id) ON DELETE RESTRICT,
        started_at             TEXT NOT NULL,
        updated_at             TEXT NOT NULL,
        condition              TEXT NOT NULL,
        crosshair_id           INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
        recommendation_id      INTEGER REFERENCES recommendations(recommendation_id) ON DELETE RESTRICT,
        task_order_group       TEXT NOT NULL
                               CHECK (task_order_group IN ('FTS','FST','TFS','TSF','SFT','STF')),
        task_order_json        TEXT NOT NULL,
        practice_order_json    TEXT NOT NULL,
        stage                  TEXT NOT NULL CHECK (stage IN ('practice','familiarization','experimental')),
        current_position       INTEGER NOT NULL CHECK (current_position BETWEEN 1 AND 3),
        current_task           TEXT CHECK (current_task IS NULL OR current_task IN ('flick','tracking','switching')),
        completed_tasks_json   TEXT NOT NULL,
        status                 TEXT NOT NULL CHECK (status IN ('in_progress','completed')),
        protocol_version       TEXT,
        protocol_snapshot_json TEXT,
        evaluation_id          INTEGER REFERENCES condition_evaluations(evaluation_id) ON DELETE RESTRICT,
        condition_position     INTEGER CHECK (condition_position IS NULL OR condition_position BETWEEN 1 AND 2)
    );
    INSERT INTO new_task_assessments (
        assessment_id, player_id, started_at, updated_at, condition, crosshair_id, recommendation_id,
        task_order_group, task_order_json, practice_order_json, stage, current_position, current_task,
        completed_tasks_json, status, protocol_version, protocol_snapshot_json)
    SELECT assessment_id, player_id, started_at, updated_at, condition, crosshair_id, recommendation_id,
        task_order_group, task_order_json, practice_order_json, stage, current_position, current_task,
        completed_tasks_json, status, protocol_version, protocol_snapshot_json
    FROM task_assessments;
    DROP TABLE task_assessments;
    ALTER TABLE new_task_assessments RENAME TO task_assessments;
    CREATE INDEX IF NOT EXISTS idx_task_assessments_player ON task_assessments(player_id, status);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_task_assessment
        ON task_assessments(player_id) WHERE status = 'in_progress';
    CREATE UNIQUE INDEX IF NOT EXISTS idx_evaluation_condition_assessment
        ON task_assessments(evaluation_id, condition_position) WHERE evaluation_id IS NOT NULL;
    CREATE TRIGGER IF NOT EXISTS task_assessment_assignment_immutable
        BEFORE UPDATE OF player_id, condition, crosshair_id, recommendation_id,
                         task_order_group, task_order_json, practice_order_json,
                         protocol_version, protocol_snapshot_json, evaluation_id, condition_position
        ON task_assessments
        BEGIN SELECT RAISE(ABORT, 'task-assessment assignment is immutable'); END;

    CREATE TABLE new_sessions (
        session_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id                   TEXT    NOT NULL REFERENCES players(player_id) ON DELETE RESTRICT,
        started_at                  TEXT    NOT NULL,
        ended_at                    TEXT,
        experiment_type             TEXT    NOT NULL CHECK (experiment_type IN ('flick', 'tracking', 'switching')),
        condition                   TEXT    NOT NULL CHECK (condition IN ('baseline', 'standard', 'candidate')),
        session_number              INTEGER NOT NULL CHECK (session_number >= 1),
        status                      TEXT    NOT NULL DEFAULT 'in_progress'
                                            CHECK (status IN ('in_progress', 'completed', 'aborted')),
        crosshair_id                INTEGER NOT NULL REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
        environment_id              INTEGER REFERENCES environments(environment_id) ON DELETE RESTRICT,
        random_seed                 INTEGER,
        task_config_json            TEXT,
        parent_session_id           INTEGER REFERENCES sessions(session_id) ON DELETE RESTRICT,
        recommendation_id           INTEGER REFERENCES recommendations(recommendation_id) ON DELETE RESTRICT,
        app_version                 TEXT,
        notes                       TEXT,
        protocol_version            TEXT,
        protocol_snapshot_json      TEXT,
        crosshair_snapshot_json     TEXT,
        assessment_id               INTEGER REFERENCES task_assessments(assessment_id) ON DELETE RESTRICT,
        assessment_stage            TEXT CHECK (assessment_stage IS NULL OR assessment_stage IN
                                        ('practice','familiarization','experimental','combined')),
        task_order_mode             TEXT CHECK (task_order_mode IS NULL OR task_order_mode IN
                                        ('counterbalanced','debug_fixed','individual')),
        task_order_group            TEXT CHECK (task_order_group IS NULL OR task_order_group IN
                                        ('FTS','FST','TFS','TSF','SFT','STF','DEBUG')),
        task_order_json             TEXT,
        task_position               INTEGER CHECK (task_position IS NULL OR task_position BETWEEN 1 AND 3),
        evaluation_id               INTEGER REFERENCES condition_evaluations(evaluation_id) ON DELETE RESTRICT,
        condition_order_group       TEXT CHECK (condition_order_group IS NULL OR condition_order_group IN ('CS','SC')),
        condition_order_json        TEXT,
        condition_position          INTEGER CHECK (condition_position IS NULL OR condition_position BETWEEN 1 AND 2),
        initial_baseline_session_id INTEGER REFERENCES sessions(session_id) ON DELETE RESTRICT,
        selected_candidate_id       INTEGER REFERENCES crosshairs(crosshair_id) ON DELETE RESTRICT,
        seed_group                  TEXT CHECK (seed_group IS NULL OR seed_group IN
                                        ('baseline','standard','candidate','practice','familiarization'))
    );
    INSERT INTO new_sessions (
        session_id, player_id, started_at, ended_at, experiment_type, condition, session_number, status,
        crosshair_id, environment_id, random_seed, task_config_json, parent_session_id, recommendation_id,
        app_version, notes, protocol_version, protocol_snapshot_json, crosshair_snapshot_json,
        assessment_id, assessment_stage, task_order_mode, task_order_group, task_order_json, task_position)
    SELECT session_id, player_id, started_at, ended_at, experiment_type, condition, session_number, status,
        crosshair_id, environment_id, random_seed, task_config_json, parent_session_id, recommendation_id,
        app_version, notes, protocol_version, protocol_snapshot_json, crosshair_snapshot_json,
        assessment_id, assessment_stage, task_order_mode, task_order_group, task_order_json, task_position
    FROM sessions;
    DROP TABLE sessions;
    ALTER TABLE new_sessions RENAME TO sessions;
    CREATE INDEX IF NOT EXISTS idx_sessions_player    ON sessions(player_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_type      ON sessions(experiment_type, condition);
    CREATE INDEX IF NOT EXISTS idx_sessions_crosshair ON sessions(crosshair_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_protocol  ON sessions(protocol_version);
    CREATE INDEX IF NOT EXISTS idx_sessions_assessment ON sessions(assessment_id, task_position);
    CREATE INDEX IF NOT EXISTS idx_sessions_task_order ON sessions(task_order_group, task_position);
    CREATE INDEX IF NOT EXISTS idx_sessions_evaluation ON sessions(evaluation_id, condition_position);
    CREATE TRIGGER IF NOT EXISTS sessions_snapshot_immutable
        BEFORE UPDATE OF protocol_version, protocol_snapshot_json, crosshair_snapshot_json ON sessions
        WHEN OLD.protocol_version IS NOT NULL OR OLD.protocol_snapshot_json IS NOT NULL
             OR OLD.crosshair_snapshot_json IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'session protocol/crosshair snapshots are immutable'); END;
    CREATE TRIGGER IF NOT EXISTS sessions_task_order_immutable
        BEFORE UPDATE OF assessment_id, assessment_stage, task_order_mode,
                         task_order_group, task_order_json, task_position ON sessions
        WHEN OLD.task_order_group IS NOT NULL OR OLD.assessment_id IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'session task-order metadata is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS sessions_condition_metadata_immutable
        BEFORE UPDATE OF condition, evaluation_id, condition_order_group, condition_order_json,
                         condition_position, initial_baseline_session_id, selected_candidate_id,
                         seed_group, random_seed ON sessions
        BEGIN SELECT RAISE(ABORT, 'session condition metadata is immutable'); END;

    UPDATE sqlite_sequence
       SET seq = MAX(seq, (SELECT p.seq FROM _phase5_sequence p WHERE p.name = sqlite_sequence.name))
     WHERE name IN (SELECT name FROM _phase5_sequence);
    INSERT INTO sqlite_sequence(name, seq)
        SELECT p.name, p.seq FROM _phase5_sequence p
        WHERE p.name NOT IN (SELECT name FROM sqlite_sequence);
    DROP TABLE _phase5_sequence;
    """,
}

# Tables whose row counts must be unchanged by a migration (verified before commit).
PRESERVED_TABLES = (
    "players", "sessions", "trials", "trial_samples", "trial_events", "crosshairs",
    "crosshair_sources", "environments", "aim_results", "recommendations",
    "recommendation_candidates", "task_assessments",
)
SCHEMA_VERSION = str(max(MIGRATIONS, default=1))

log = get_logger("database")


class DatabaseError(RuntimeError):
    """Raised when the database cannot be opened or initialized."""


class Database:
    """Owns a single SQLite connection for the application.

    Foreign keys are enabled per-connection (SQLite requires this) and rows
    are returned as ``sqlite3.Row`` for name-based access.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path) if str(db_path) != ":memory:" else db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DatabaseError("Database is not open. Call open() first.")
        return self._conn

    def open(self) -> "Database":
        """Open the connection and create/upgrade the schema if needed."""
        try:
            if isinstance(self.db_path, Path):
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self.initialize_schema()
        except sqlite3.Error as exc:
            log.exception("db_open_failed path=%s", self.db_path)
            raise DatabaseError(f"Could not open database at {self.db_path}: {exc}") from exc
        log.info("db_opened path=%s schema_version=%s", self.db_path, self.schema_version())
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            log.info("db_closed path=%s", self.db_path)

    def __enter__(self) -> "Database":
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def initialize_schema(self) -> None:
        """Apply ``schema.sql`` then pending migrations. Safe to call repeatedly."""
        script = SCHEMA_PATH.read_text(encoding="utf-8")
        conn = self.connection
        conn.executescript(script)
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1') "
            "ON CONFLICT(key) DO NOTHING"
        )
        conn.commit()
        current = int(self.schema_version() or 1)
        pending = sorted(v for v in MIGRATIONS if v > current)
        if not pending:
            return
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise DatabaseError(f"Database integrity check failed before migration: {integrity}")
        if self._has_research_data():
            self.backup(f"schema{current}")
        # Table rebuilds need foreign keys off (SQLite ignores this PRAGMA inside a transaction).
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            for version in pending:
                log.info("db_migrate from=%s to=%s", current, version)
                before = self._row_counts()
                conn.executescript(
                    "BEGIN;\n" + MIGRATIONS[version] + "\n"
                    f"UPDATE schema_meta SET value = '{version}' WHERE key = 'schema_version';\n"
                )
                problems = [
                    f"{table}: {count} -> {self._row_count(table)}"
                    for table, count in before.items() if self._row_count(table) != count
                ]
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if problems or violations:
                    conn.rollback()
                    raise DatabaseError(
                        f"Migration to schema {version} rolled back: row counts changed {problems} "
                        f"or foreign-key violations {len(violations)}"
                    )
                conn.commit()
                current = version
        finally:
            if conn.in_transaction:
                conn.rollback()
            conn.execute("PRAGMA foreign_keys = ON")

    def _row_count(self, table: str) -> int | None:
        exists = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if not exists:
            return None
        return int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def _row_counts(self) -> dict[str, int]:
        counts = {table: self._row_count(table) for table in PRESERVED_TABLES}
        return {table: count for table, count in counts.items() if count is not None}

    def _has_research_data(self) -> bool:
        if not isinstance(self.db_path, Path):
            return False
        return any(
            self.connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
            for table in ("players", "sessions", "crosshairs")
        )

    def backup(self, label: str) -> Path | None:
        """Copy the database to ``<db dir>/backups/`` (SQLite online backup; the original is untouched)."""
        if not isinstance(self.db_path, Path):
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = self.db_path.parent / "backups" / f"{self.db_path.stem}_{label}_{stamp}.db"
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(str(target))
        try:
            self.connection.backup(destination)
        finally:
            destination.close()
        log.info("db_backup path=%s", target)
        return target

    def schema_version(self) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return row["value"] if row else None

    def table_names(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit on success, roll back on any exception (and re-raise)."""
        conn = self.connection
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
