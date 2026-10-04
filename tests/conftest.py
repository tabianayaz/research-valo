"""Shared deterministic fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.data.database import Database  # noqa: E402
from app.data.models import (  # noqa: E402
    Condition,
    CrosshairRecord,
    CrosshairRole,
    ExperimentType,
    Player,
    Session,
)
from app.data.repository import Repository  # noqa: E402


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.db").open()
    yield database
    database.close()


@pytest.fixture
def repo(db: Database) -> Repository:
    return Repository(db)


@pytest.fixture
def player(repo: Repository) -> Player:
    return repo.save_player(Player(player_id="P-TEST", mouse_dpi=800, sensitivity=0.5, edpi=400))


@pytest.fixture
def crosshair(repo: Repository) -> CrosshairRecord:
    return repo.add_crosshair(
        CrosshairRecord(
            name="Test baseline",
            role=CrosshairRole.BASELINE,
            color="#00FF00",
            size=6,
            thickness=2,
            gap=3,
            outline_enabled=True,
            outline_thickness=1,
            opacity=1.0,
        )
    )


@pytest.fixture
def session(repo: Repository, player: Player, crosshair: CrosshairRecord) -> Session:
    return repo.create_session(
        Session(
            player_id=player.player_id,
            experiment_type=ExperimentType.FLICK,
            condition=Condition.BASELINE,
            session_number=1,
            crosshair_id=crosshair.crosshair_id,
            random_seed=12345,
            task_config={"trials": 30},
        )
    )


@pytest.fixture(autouse=True)
def _english_ui():
    """The UI language is process-wide; every test starts (and ends) in English."""
    from app.i18n import Language, translator

    translator.set_language(Language.EN)
    yield
    translator.set_language(Language.EN)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def context(qapp, tmp_path: Path):
    """Full application context on a temporary database with a selected participant."""
    from app.config.settings import load_settings
    from app.main import build_context

    settings = load_settings(data_dir=tmp_path)
    settings.ensure_directories()
    ctx = build_context(settings)
    # Tests that exercise the practice block enable it explicitly (tests/test_protocol.py).
    ctx.research.protocol["practice_enabled"] = False
    ctx.set_current_player(ctx.repository.save_player(Player(player_id="P-TASK")))
    yield ctx
    ctx.database.close()
