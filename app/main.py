"""Application entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app import __version__
from app.app_context import AppContext
from app.config.research import load_research_parameters
from app.config.settings import APP_NAME, AppSettings, load_settings
from app.crosshair.presets import ensure_baseline
from app.data.database import Database, DatabaseError
from app.utils.validators import ValidationError
from app.data.repository import Repository
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.utils.logging import configure_logging, install_excepthook


def build_context(settings: AppSettings, research_path: Path | None = None) -> AppContext:
    """Open the database (creating it if missing) and assemble shared state."""
    research = load_research_parameters(research_path)
    database = Database(settings.db_path).open()
    repository = Repository(database)
    baseline = ensure_baseline(repository, research)
    return AppContext(
        settings=settings,
        database=database,
        repository=repository,
        research=research,
        baseline_crosshair=baseline,
    )


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    settings.ensure_directories()
    logger = configure_logging(settings.logs_dir)
    install_excepthook(logger)
    logger.info("app_start version=%s data_dir=%s", __version__, settings.data_dir)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    apply_theme(app)

    try:
        context = build_context(settings)
    except DatabaseError as exc:
        QMessageBox.critical(None, APP_NAME, f"The database could not be opened.\n\n{exc}")
        return 1
    except ValidationError as exc:
        logger.error("research_parameters_invalid error=%s", exc)
        QMessageBox.critical(None, APP_NAME, f"Research parameters are invalid.\n\n{exc}")
        return 1

    window = MainWindow(context)
    window.show()
    try:
        exit_code = app.exec()
    finally:
        context.database.close()
        logger.info("app_exit")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
