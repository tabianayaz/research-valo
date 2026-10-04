"""Headless smoke tests for the main window and navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import load_settings
from app.main import build_context
from app.ui.components import PageId
from app.ui.main_window import MainWindow


@pytest.fixture
def window(qapp, tmp_path: Path):
    settings = load_settings(data_dir=tmp_path)
    settings.ensure_directories()
    context = build_context(settings)
    win = MainWindow(context)
    yield win
    win.close()
    context.database.close()


def test_starts_on_home(window: MainWindow) -> None:
    assert window.current_page_id() == PageId.HOME


def test_every_page_is_navigable(window: MainWindow) -> None:
    for page_id in PageId:
        window.navigate(page_id)
        assert window.current_page_id() == page_id
        assert window.nav_buttons[page_id].isChecked()


def test_setup_page_saves_player_and_advances(window: MainWindow) -> None:
    window.navigate(PageId.SETUP)
    page = window.pages[PageId.SETUP]
    page.player_id_edit.setText("P-UI01")
    page.dpi_spin.setValue(800)
    page.sensitivity_spin.setValue(0.5)
    page.save_button.click()

    player = window.context.repository.get_player("P-UI01")
    assert player is not None
    assert player.edpi == pytest.approx(400.0)
    assert window.context.current_player.player_id == "P-UI01"
    assert window.current_page_id() == PageId.CROSSHAIR


def test_baseline_created_on_startup(window: MainWindow) -> None:
    baseline = window.context.baseline_crosshair
    assert baseline.crosshair_id is not None
    assert baseline.role == "baseline"


def test_crosshair_editor_validation(window: MainWindow) -> None:
    window.navigate(f"{PageId.CROSSHAIR}:editor")
    editor = window.pages[PageId.CROSSHAIR].editor
    assert editor.save_button.isEnabled()
    editor.color_edit.setText("#12")
    assert not editor.save_button.isEnabled()
    assert editor.banner.property("kind") == "error"
    editor.color_edit.setText("#00FF00")
    assert editor.current_config().color == "#00FF00"
    editor.name_edit.setText("green test")
    editor.save_button.click()
    names = [c.name for c in window.context.repository.list_crosshairs()]
    assert "green test" in names


def test_crosshair_database_import_and_listing(window: MainWindow) -> None:
    from app.scraper.importer import Provenance, import_valorant_codes

    import_valorant_codes(
        window.context.repository,
        ["0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0", "0;P;c;1;o;1;d;1;0b;0;1b;0"],
        Provenance("test"),
        window.context.research.parameter_ranges,
    )
    window.navigate(f"{PageId.CROSSHAIR}:database")
    view = window.pages[PageId.CROSSHAIR].database
    assert view.table.rowCount() == 2
    view.table.selectRow(0)
    assert view.open_button.isEnabled()
    view.open_button.click()
    page = window.pages[PageId.CROSSHAIR]
    assert page.tabs.currentWidget() is page.editor
    assert page.editor.current_config().color == "#00FFFF"


def test_setup_page_rejects_invalid_id(window: MainWindow) -> None:
    window.navigate(PageId.SETUP)
    page = window.pages[PageId.SETUP]
    page.player_id_edit.setText("x")
    page.save_button.click()
    assert window.context.repository.list_players() == []
    assert window.current_page_id() == PageId.SETUP
    assert page.banner.property("kind") == "error"
