"""Render each page of the main window to PNG (for documentation / visual QA).

Usage: python scripts/render_screens.py [output_dir] [--ja]   (--ja renders the Japanese UI)
Uses a throwaway database so the real research database is never touched.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.data.models import Player  # noqa: E402
from app.ui.flick_window import FlickExperimentWindow  # noqa: E402
from app.ui.switching_window import SwitchingExperimentWindow  # noqa: E402
from app.ui.tracking_window import TrackingExperimentWindow  # noqa: E402

from app.config.settings import load_settings  # noqa: E402
from app.main import build_context  # noqa: E402
from app.scraper.importer import Provenance, import_valorant_codes  # noqa: E402
from app.ui.components import PageId  # noqa: E402
from app.ui.crosshair_database import ImportDialog  # noqa: E402
from app.ui.source_update_dialog import LiquipediaUpdateDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402


def render_task_states(app: QApplication, context, out_dir: Path) -> None:
    """Grab intro, start marker and stimulus screens of every task (temporary database only)."""
    context.set_current_player(context.repository.save_player(Player(player_id="P-SCREENSHOT")))
    for name, window_class in (("flick", FlickExperimentWindow), ("tracking", TrackingExperimentWindow),
                               ("switching", SwitchingExperimentWindow)):
        window = window_class(context)
        window.resize(1280, 800)
        window.show()
        app.processEvents()
        window.grab().save(str(out_dir / f"{name}_intro.png"))
        window.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
        center = window._center_px()
        dpr = window.devicePixelRatioF()
        window.cursor_px = QPoint(round(center.x() + 60 * dpr), round(center.y() + 40 * dpr))
        window.update()
        app.processEvents()
        window.grab().save(str(out_dir / f"{name}_start_marker.png"))
        window.cursor_px = center.toPoint()
        window._on_start_click(time.perf_counter())
        window.stabilize_timer.stop()
        window._on_stable()
        window.foreperiod_timer.stop()
        window._show_target()
        app.processEvents()
        window._onset_fallback()
        window.grab().save(str(out_dir / f"{name}_target.png"))
        window.close()


def _simulate_flick(app: QApplication, context, run=None, trials: int = 8) -> int:
    from PySide6.QtCore import QPointF

    from experiment_helpers import click, move, start_trial

    context.research.flick_task.update(trial_count=trials)
    context.research.protocol["practice_enabled"] = False
    window = FlickExperimentWindow(context, run)
    window.resize(1280, 800)
    window.show()
    window.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
    for i in range(trials):
        start_trial(window, app)
        target = window._current_target()
        point = QPointF(target.x + (6 * (i % 4)), target.y + (25 if i % 3 == 0 else 0))
        move(window, point)
        click(window, point)
    session_id = window.session.session_id
    window.close()
    return session_id


def _grab(app: QApplication, window, path: Path) -> None:
    for _ in range(5):  # widgets added at runtime are shown and laid out over several passes
        app.processEvents()
    window.grab().save(str(path))


def render_pipeline(app: QApplication, window, context, out_dir: Path) -> None:
    """Simulated baseline -> recommendation -> candidate session (temporary database only)."""
    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    from app.data.models import Condition
    from app.ui.experiment_window import RunSetup

    baseline_id = _simulate_flick(app, context)
    window.navigate(f"{PageId.RESULTS}:{baseline_id}")
    _grab(app, window, out_dir / "pipeline_results.png")

    window.navigate(PageId.RECOMMENDATION)
    window.pages[PageId.RECOMMENDATION].generate()
    _grab(app, window, out_dir / "pipeline_recommendation.png")

    rec = context.repository.list_recommendations()[0]
    crosshair_id = rec["candidates"][0]["crosshair_id"]
    window.navigate(f"{PageId.ASSESSMENT}:candidate:{rec['recommendation_id']}:{crosshair_id}")
    _grab(app, window, out_dir / "pipeline_assessment_candidate.png")

    run = RunSetup(context.repository.get_crosshair(crosshair_id), Condition.CANDIDATE, baseline_id,
                   rec["recommendation_id"])
    candidate_id = _simulate_flick(app, context, run)
    for target, name in ((f"{PageId.COMPARISON}:{candidate_id}", "pipeline_comparison"),
                         (str(PageId.HISTORY), "pipeline_history")):
        window.navigate(target)
        _grab(app, window, out_dir / f"{name}.png")


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--ja"]
    japanese = "--ja" in sys.argv[1:]
    out_dir = Path(args[0]) if args else Path(tempfile.mkdtemp(prefix="screens_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    apply_theme(app)
    if japanese:
        from app.i18n import Language, translator

        translator.set_language(Language.JA)  # MainWindow installs the window translation filter
    with tempfile.TemporaryDirectory() as data_dir:
        settings = load_settings(data_dir=Path(data_dir))
        settings.ensure_directories()
        context = build_context(settings)
        codes = PROJECT_ROOT / "assets" / "crosshair_sources" / "researcher_provided_valorant_codes.txt"
        import_valorant_codes(
            context.repository, codes.read_text(encoding="utf-8").splitlines(),
            Provenance("Researcher-provided list"), context.research.parameter_ranges,
        )
        window = MainWindow(context)
        window.resize(1280, 860)
        window.show()
        targets = [str(p) for p in PageId] + [
            f"{PageId.CROSSHAIR}:editor", f"{PageId.CROSSHAIR}:database",
        ]
        for target in targets:
            window.navigate(target)
            app.processEvents()
            window.grab().save(str(out_dir / f"{target.replace(':', '_')}.png"))
        dialogs = {
            "dialog_import": ImportDialog(context, window),
            "dialog_liquipedia": LiquipediaUpdateDialog(context, window),
        }
        for name, dialog in dialogs.items():
            dialog.show()
            app.processEvents()
            dialog.grab().save(str(out_dir / f"{name}.png"))
            dialog.close()
        render_task_states(app, context, out_dir)
        render_pipeline(app, window, context, out_dir)
        window.close()
        context.database.close()
    print(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
