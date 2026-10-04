"""Deleting user-created custom crosshairs without touching the research record."""

from __future__ import annotations

import pytest

from app.data.models import (
    Condition,
    CrosshairRecord,
    CrosshairRole,
    ExperimentType,
    Player,
    Session,
)
from app.data.repository import Repository, RepositoryError


def _custom(repo: Repository, name: str = "My custom") -> CrosshairRecord:
    return repo.add_crosshair(CrosshairRecord(
        name=name, role=CrosshairRole.CUSTOM, color="#FF00FF", size=4, thickness=2, gap=1,
        outline_enabled=False, outline_thickness=1, opacity=1.0,
    ))


def test_unused_custom_crosshair_is_deleted(repo: Repository) -> None:
    custom = _custom(repo)
    assert repo.crosshair_usage(custom.crosshair_id) == 0
    repo.delete_custom_crosshair(custom.crosshair_id)
    assert repo.get_crosshair(custom.crosshair_id) is None


def test_baseline_and_candidate_crosshairs_cannot_be_deleted(
    repo: Repository, crosshair: CrosshairRecord
) -> None:
    candidate = repo.add_crosshair(CrosshairRecord(
        name="Candidate", role=CrosshairRole.CANDIDATE, color="#FFFFFF", size=3, thickness=1,
        gap=2, outline_enabled=False, outline_thickness=1, opacity=1.0,
    ))
    for record in (crosshair, candidate):
        with pytest.raises(RepositoryError, match="Only custom"):
            repo.delete_custom_crosshair(record.crosshair_id)
        assert repo.get_crosshair(record.crosshair_id) is not None


def test_custom_crosshair_used_by_a_session_is_kept(repo: Repository, player: Player) -> None:
    custom = _custom(repo)
    session = repo.create_session(Session(
        player_id=player.player_id, experiment_type=ExperimentType.FLICK,
        condition=Condition.CANDIDATE, session_number=1, crosshair_id=custom.crosshair_id,
        random_seed=1, task_config={},
    ))
    assert repo.crosshair_usage(custom.crosshair_id) == 1
    with pytest.raises(RepositoryError, match="kept"):
        repo.delete_custom_crosshair(custom.crosshair_id)
    assert repo.get_crosshair(custom.crosshair_id) is not None
    assert repo.get_session(session.session_id) is not None


def test_missing_crosshair_raises(repo: Repository) -> None:
    with pytest.raises(RepositoryError, match="does not exist"):
        repo.delete_custom_crosshair(9999)


def test_editor_delete_button_only_for_custom_and_deletes(context) -> None:
    from app.ui.crosshair_editor import CrosshairEditor

    repo = context.repository
    custom = _custom(repo, "Delete me")
    editor = CrosshairEditor(context)
    editor.refresh_choices()

    baseline_index = editor.load_combo.findData(context.baseline_crosshair.crosshair_id)
    editor.load_combo.setCurrentIndex(baseline_index)
    assert not editor.delete_button.isEnabled()
    assert editor.delete_selected(confirm=False) is False

    editor.load_combo.setCurrentIndex(editor.load_combo.findData(custom.crosshair_id))
    assert editor.delete_button.isEnabled()
    assert editor.delete_selected(confirm=False) is True
    assert repo.get_crosshair(custom.crosshair_id) is None
    assert editor.load_combo.findData(custom.crosshair_id) == -1


def test_editor_refuses_custom_crosshair_with_sessions(context) -> None:
    from app.ui.crosshair_editor import CrosshairEditor

    repo = context.repository
    custom = _custom(repo, "Used")
    repo.create_session(Session(
        player_id=context.current_player.player_id, experiment_type=ExperimentType.FLICK,
        condition=Condition.CANDIDATE, session_number=1, crosshair_id=custom.crosshair_id,
        random_seed=1, task_config={},
    ))
    editor = CrosshairEditor(context)
    editor.refresh_choices()
    editor.load_combo.setCurrentIndex(editor.load_combo.findData(custom.crosshair_id))
    assert editor.delete_selected(confirm=False) is False
    assert repo.get_crosshair(custom.crosshair_id) is not None
