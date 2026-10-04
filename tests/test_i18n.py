"""English/Japanese display localization (display only; stored/exported values stay English)."""

from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import pytest
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel, QTableWidget, QTabWidget

from app.config.settings import load_settings
from app.i18n import Language, display, tr, tr_message, translator
from app.i18n_ja import JA
from app.main import build_context
from app.ui.components import PageId
from app.ui.main_window import NAV_ITEMS, MainWindow

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def window(qapp, tmp_path: Path):
    settings = load_settings(data_dir=tmp_path)
    settings.ensure_directories()
    context = build_context(settings)
    win = MainWindow(context)
    yield win
    win.close()
    context.database.close()


def _visible_texts(win) -> list[str]:
    """Every text in a widget tree (labels, buttons, tabs, table headers, combo items)."""
    texts: list[str] = []
    for widget in win.findChildren(QLabel):
        texts.append(widget.text())
    for widget in win.findChildren(QAbstractButton):
        texts.append(widget.text())
        texts.append(widget.toolTip())
    for widget in win.findChildren(QTabWidget):
        texts.extend(widget.tabText(i) for i in range(widget.count()))
    for widget in win.findChildren(QTableWidget):
        for column in range(widget.columnCount()):
            item = widget.horizontalHeaderItem(column)
            texts.append(item.text() if item else "")
    for widget in win.findChildren(QComboBox):
        texts.extend(widget.itemText(i) for i in range(widget.count()))
    return texts


# ---------------------------------------------------------------- language state
def test_application_starts_in_english(window: MainWindow) -> None:
    assert translator.language == Language.EN
    assert window.language_button.text() == "日本語"
    assert window.nav_buttons[PageId.HOME].text() == "Home"
    assert window.player_status.text() == "No participant selected"


def test_toggle_switches_navigation_and_status_bar(window: MainWindow) -> None:
    window.language_button.click()
    assert translator.language == Language.JA
    assert window.language_button.text() == "English"
    for page_id, english in NAV_ITEMS:
        assert window.nav_buttons[page_id].text() == JA[english]
    assert window.player_status.text() == "参加者が選択されていません"
    assert window.db_status.text().startswith("データベース: ")

    window.language_button.click()
    assert translator.language == Language.EN
    assert window.nav_buttons[PageId.RESULTS].text() == "Results"
    assert window.db_status.text().startswith("Database: ")


def test_every_page_translates_and_round_trips(window: MainWindow) -> None:
    for page_id in PageId:
        window.navigate(page_id)
    english = {}
    for page_id in PageId:
        window.navigate(page_id)
        english[page_id] = _visible_texts(window.pages[page_id])
    sidebar = _visible_texts(window.nav_buttons[PageId.HOME].parentWidget())

    window.language_button.click()
    titles = {page_id: window.pages[page_id].findChild(QLabel, "pageTitle").text() for page_id in PageId}
    assert titles[PageId.HOME] == "ホーム"
    assert titles[PageId.SETUP] == "参加者設定"
    assert titles[PageId.ASSESSMENT] == "エイム測定"
    for page_id in PageId:
        window.navigate(page_id)  # dynamic text is rebuilt in Japanese on show

    window.language_button.click()
    # Hidden pages rebuild their dynamic text when shown; static text is restored at once.
    for page_id in PageId:
        window.navigate(page_id)
        assert _visible_texts(window.pages[page_id]) == english[page_id], page_id
    assert _visible_texts(window.nav_buttons[PageId.HOME].parentWidget()) == sidebar


def test_table_headers_and_tabs_follow_language(window: MainWindow) -> None:
    window.navigate(PageId.HISTORY)
    window.language_button.click()
    history = window.pages[PageId.HISTORY]
    headers = [history.table.horizontalHeaderItem(c).text() for c in range(history.table.columnCount())]
    assert headers[:4] == ["セッション", "選手", "開始 (UTC)", "課題"]
    crosshair = window.pages[PageId.CROSSHAIR]
    assert crosshair.tabs.tabText(0) == "標準クロスヘア"


def test_assessment_status_text_in_japanese(window: MainWindow) -> None:
    from app.data.models import Player

    context = window.context
    context.set_current_player(context.repository.save_player(Player(player_id="P-JA01")))
    window.navigate(PageId.ASSESSMENT)
    window.language_button.click()
    page = window.pages[PageId.ASSESSMENT]
    assert page.controlled_button.text() == "統制測定を開始"
    assert page.banner.text() == "参加者: P-JA01"
    window.language_button.click()
    assert page.controlled_button.text() == "Start controlled assessment"
    assert page.banner.text() == "Participant: P-JA01"


# ------------------------------------------------------- stored values unchanged
def test_setup_combo_saves_english_values_while_japanese(window: MainWindow) -> None:
    window.navigate(PageId.SETUP)
    window.language_button.click()
    page = window.pages[PageId.SETUP]
    page.fps_experience_combo.setCurrentIndex(4)
    page.aim_training_combo.setCurrentIndex(5)
    assert page.fps_experience_combo.currentText() == "3年以上"
    page.player_id_edit.setText("P-JA02")
    page.save_button.click()

    player = window.context.repository.get_player("P-JA02")
    assert player.fps_experience == "More than 3 years"
    assert player.aim_training_frequency == "Daily"

    window.language_button.click()
    page._populate(player)
    assert page.fps_experience_combo.currentText() == "More than 3 years"


def test_setup_validation_message_is_translated(window: MainWindow) -> None:
    window.navigate(PageId.SETUP)
    window.language_button.click()
    page = window.pages[PageId.SETUP]
    page.player_id_edit.setText("x")
    page.save_button.click()
    assert page.banner.text().startswith("参加者IDは")
    window.language_button.click()
    assert page.banner.text().startswith("Player ID must be")


def test_comparison_display_translated_but_export_values_stay_english() -> None:
    from app.analysis.comparison import CSV_HEADER, MetricComparison

    translator.set_language(Language.JA)
    metric = MetricComparison("hit_rate", 0.5, 0.75)
    assert metric.direction_text() == "higher with candidate"  # exported value
    assert metric.desirable_direction == "higher"
    assert tr(metric.direction_text()) == "候補の方が高い"  # display only
    assert "direction" in CSV_HEADER


def test_data_and_export_layers_do_not_use_translations() -> None:
    for folder in ("analysis", "data", "experiment", "recommendation", "scraper"):
        for path in (ROOT / "app" / folder).glob("*.py"):
            assert "app.i18n" not in path.read_text(encoding="utf-8"), path


def test_display_keeps_canonical_value_in_english() -> None:
    assert display("baseline") == "baseline"
    assert display("in_progress") == "in_progress"
    translator.set_language(Language.JA)
    assert display("baseline") == "ベースライン"
    assert display("completed") == "完了"
    assert display("not-a-code") == "not-a-code"


# ---------------------------------------------------------- experiment windows
def test_experiment_intro_and_done_text_in_japanese(context) -> None:
    from app.ui.flick_window import FlickExperimentWindow

    window = FlickExperimentWindow(context)
    try:
        english = window._intro_text()
        assert english[0] == "Flick Aim"
        assert "Press Space to begin" in english
        translator.set_language(Language.JA)
        japanese = window._intro_text()
        assert japanese[0] == "フリックエイム"
        assert "スペースキーで開始" in japanese
        assert "Esc キーで中断" in japanese
        assert window._done_text().startswith("セッションを終了しました")
    finally:
        window.close()


# ------------------------------------------------------------------ dictionary
def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_japanese_strings_keep_placeholders() -> None:
    for english, japanese in JA.items():
        assert _placeholders(english) == _placeholders(japanese), english


def _literal_tr_keys() -> set[str]:
    keys: set[str] = set()
    for path in list((ROOT / "app" / "ui").glob("*.py")) + [ROOT / "app" / "i18n.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            index = 1 if name == "set_tr_text" else 0
            if name not in {"tr", "label", "primary_button", "secondary_button", "Card", "MetricTile",
                            "show_message", "set_title", "set_tr_text", "_show_empty"}:
                continue
            if len(node.args) <= index:
                continue
            arg = node.args[index]
            candidates = [arg] if not isinstance(arg, ast.IfExp) else [arg.body, arg.orelse]
            for candidate in candidates:
                if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
                    keys.add(candidate.value)
    return {key for key in keys if re.search(r"[A-Za-z]", key)}


def test_every_literal_ui_string_has_a_japanese_translation() -> None:
    # Data-like literals that are intentionally not translated.
    allowed = {"PySide6", "Python"}
    missing = sorted(key for key in _literal_tr_keys() if key not in JA and key not in allowed)
    assert missing == []


def test_listed_ui_constants_are_translated() -> None:
    from app.analysis.metrics import METRICS
    from app.recommendation.engine import COMPONENT_LABELS
    from app.ui import comparison_page, crosshair_database, history_page, results_page, setup_page
    from app.ui.aim_selection_page import TASKS
    from app.ui.home_page import WORKFLOW_STEPS
    from app.ui.recommendation_page import STATUS_TEXT

    expected = [english for _, english in NAV_ITEMS]
    expected += setup_page.FPS_EXPERIENCE_OPTIONS + setup_page.AIM_TRAINING_OPTIONS
    expected += history_page.COLUMNS + history_page.RECOMMENDATION_COLUMNS
    expected += results_page.POINTING_COLUMNS + results_page.TRACKING_COLUMNS
    expected += comparison_page.COLUMNS + crosshair_database.COLUMNS
    expected += [text for text, _ in crosshair_database.FILTERS]
    expected += list(STATUS_TEXT.values()) + list(COMPONENT_LABELS.values())
    expected += [text for _, name, description in WORKFLOW_STEPS for text in (name, description)]
    expected += [text for title, description, _ in TASKS.values() for text in (title, description)]
    expected += [text for definition in METRICS.values() for text in (definition.label, definition.description)]
    assert sorted(set(expected) - set(JA)) == []


def test_dynamic_validation_messages_are_translated() -> None:
    message = "size must be between 1 and 20 (got 40)."
    assert tr_message(message) == message
    translator.set_language(Language.JA)
    assert tr_message(message) == "サイズは1〜20の範囲で指定してください（入力値: 40）。"
    assert tr_message("unmapped message") == "unmapped message"
    note = "Placeholder task parameters (flick_task.confirmed = false)."
    assert tr_message(note) == "仮の課題パラメータです（flick_task.confirmed = false）。"
