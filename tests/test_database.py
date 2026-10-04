from __future__ import annotations

from pathlib import Path

from app.data.database import SCHEMA_VERSION, Database

EXPECTED_TABLES = {
    "players",
    "sessions",
    "crosshairs",
    "crosshair_sources",
    "environments",
    "trials",
    "trial_samples",
    "trial_events",
    "aim_results",
    "recommendations",
    "recommendation_candidates",
    "schema_meta",
}


def test_database_is_created_automatically(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "app.db"
    with Database(db_path) as db:
        assert db_path.exists()
        assert EXPECTED_TABLES.issubset(set(db.table_names()))
        assert db.schema_version() == SCHEMA_VERSION


def test_initialization_is_idempotent(db: Database) -> None:
    db.initialize_schema()
    db.initialize_schema()
    assert EXPECTED_TABLES.issubset(set(db.table_names()))


def test_foreign_keys_enabled(db: Database) -> None:
    assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_v1_database_is_migrated(tmp_path: Path) -> None:
    import sqlite3

    from app.data.database import SCHEMA_PATH

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
    conn.execute(
        "INSERT INTO players(player_id, created_at, updated_at) VALUES ('P-OLD', 'x', 'x')"
    )
    conn.commit()
    conn.close()

    with Database(path) as db:
        assert db.schema_version() == SCHEMA_VERSION
        columns = {r["name"] for r in db.connection.execute("PRAGMA table_info(crosshairs)")}
        assert "fidelity" in columns
        assert db.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 1


def test_reopen_preserves_data(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    with Database(path) as db:
        db.connection.execute(
            "INSERT INTO players(player_id, created_at, updated_at) VALUES ('P-1', 'x', 'x')"
        )
        db.connection.commit()
    with Database(path) as db:
        count = db.connection.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        assert count == 1
