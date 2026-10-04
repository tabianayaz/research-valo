from __future__ import annotations

import sqlite3

import pytest

from app.data.models import (
    Condition,
    CrosshairRecord,
    Environment,
    ExperimentType,
    Player,
    Session,
    SessionStatus,
    Trial,
    TrialEvent,
    TrialResult,
    TrialSample,
)
from app.data.repository import Repository, RepositoryError
from app.utils.validators import ValidationError


def test_save_and_get_player(repo: Repository) -> None:
    saved = repo.save_player(Player(player_id="P-0001", mouse_dpi=1600, sensitivity=0.3, edpi=480))
    loaded = repo.get_player("P-0001")
    assert loaded is not None
    assert loaded.mouse_dpi == 1600
    assert loaded.created_at == saved.created_at


def test_update_player_keeps_created_at(repo: Repository) -> None:
    first = repo.save_player(Player(player_id="P-0001", mouse_dpi=800))
    second = repo.save_player(Player(player_id="P-0001", mouse_dpi=1600))
    assert second.created_at == first.created_at
    assert repo.get_player("P-0001").mouse_dpi == 1600
    assert len(repo.list_players()) == 1


@pytest.mark.parametrize("bad_id", ["", "x", "has space", "名前", "a" * 33, "bad!id"])
def test_invalid_player_id_rejected(repo: Repository, bad_id: str) -> None:
    with pytest.raises(ValidationError):
        repo.save_player(Player(player_id=bad_id))


def test_non_positive_dpi_rejected(repo: Repository) -> None:
    with pytest.raises(ValidationError):
        repo.save_player(Player(player_id="P-1", mouse_dpi=0))


def test_crosshair_roundtrip(repo: Repository, crosshair: CrosshairRecord) -> None:
    loaded = repo.get_crosshair(crosshair.crosshair_id)
    assert loaded is not None
    assert loaded.color == "#00FF00"
    assert loaded.outline_enabled is True
    assert len(repo.list_crosshairs()) == 1


def test_session_lifecycle(repo: Repository, session: Session) -> None:
    assert session.session_id is not None
    assert repo.get_session(session.session_id).status == SessionStatus.IN_PROGRESS
    assert repo.get_session(session.session_id).task_config == {"trials": 30}
    repo.finish_session(session.session_id, SessionStatus.COMPLETED)
    finished = repo.get_session(session.session_id)
    assert finished.status == SessionStatus.COMPLETED
    assert finished.ended_at is not None
    with pytest.raises(RepositoryError):
        repo.finish_session(session.session_id, SessionStatus.ABORTED)


def test_session_requires_known_player(repo: Repository, crosshair: CrosshairRecord) -> None:
    with pytest.raises(RepositoryError):
        repo.create_session(
            Session(
                player_id="unknown",
                experiment_type=ExperimentType.FLICK,
                condition=Condition.BASELINE,
                session_number=1,
                crosshair_id=crosshair.crosshair_id,
            )
        )


def test_session_requires_existing_crosshair(repo: Repository, player: Player) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_session(
            Session(
                player_id=player.player_id,
                experiment_type=ExperimentType.FLICK,
                condition=Condition.BASELINE,
                session_number=1,
                crosshair_id=999,
            )
        )


def test_next_session_number(repo: Repository, player: Player, session: Session) -> None:
    assert repo.next_session_number(player.player_id) == 2
    assert repo.next_session_number("nobody") == 1


def test_environment_insert(repo: Repository) -> None:
    env = repo.add_environment(
        Environment(display_width=1920, display_height=1080, extra={"note": "lab A"})
    )
    assert env.environment_id is not None


def _flick_trial(session_id: int, number: int) -> Trial:
    return Trial(
        session_id=session_id,
        trial_number=number,
        task_type=ExperimentType.FLICK,
        result=TrialResult.HIT,
        target_id=f"T{number}",
        target_x=100.0,
        target_y=200.0,
        target_size=30.0,
        reaction_time_ms=412.5,
        error_distance=3.2,
        extra={"seed_index": number},
    )


def test_trial_with_samples_and_events(repo: Repository, session: Session) -> None:
    trial = repo.add_trial(
        _flick_trial(session.session_id, 1),
        samples=[TrialSample(0.0, 10, 10), TrialSample(8.3, 20, 25, on_target=False)],
        events=[TrialEvent(412.5, "click", 101, 199, is_hit=True)],
    )
    trials = repo.list_trials(session.session_id)
    assert len(trials) == 1
    assert trials[0].reaction_time_ms == pytest.approx(412.5)
    assert trials[0].extra == {"seed_index": 1}
    samples = repo.list_samples(trial.trial_id)
    assert [s.t_ms for s in samples] == [0.0, 8.3]
    assert samples[1].on_target is False
    assert repo.list_events(trial.trial_id)[0].is_hit is True


def test_duplicate_trial_number_rejected(repo: Repository, session: Session) -> None:
    repo.add_trial(_flick_trial(session.session_id, 1))
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_trial(_flick_trial(session.session_id, 1))


def test_failed_trial_insert_is_atomic(repo: Repository, session: Session) -> None:
    bad_samples = [TrialSample(0.0, 1, 1), TrialSample(1.0, None, None)]  # type: ignore[arg-type]
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_trial(_flick_trial(session.session_id, 1), samples=bad_samples)
    assert repo.list_trials(session.session_id) == []


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE trials SET reaction_time_ms = 1",
        "DELETE FROM trials",
        "UPDATE trial_samples SET cursor_x = 0",
        "DELETE FROM trial_samples",
        "UPDATE trial_events SET x = 0",
        "DELETE FROM trial_events",
    ],
)
def test_raw_data_is_immutable(repo: Repository, session: Session, statement: str) -> None:
    repo.add_trial(
        _flick_trial(session.session_id, 1),
        samples=[TrialSample(0.0, 1, 1)],
        events=[TrialEvent(1.0, "click", 1, 1, True)],
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repo.db.connection.execute(statement)


def test_session_summaries(repo: Repository, session: Session) -> None:
    repo.add_trial(_flick_trial(session.session_id, 1))
    repo.add_trial(_flick_trial(session.session_id, 2))
    summaries = repo.list_session_summaries()
    assert len(summaries) == 1
    assert summaries[0].trial_count == 2
    assert summaries[0].crosshair_name == "Test baseline"
