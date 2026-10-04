"""Manual "Update Database" operation for web sources (never runs automatically)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.app_context import AppContext
from app.scraper.crosshair_scraper import (
    LIQUIPEDIA_CACHE_TTL_S,
    LIQUIPEDIA_LICENSE,
    LIQUIPEDIA_MIN_INTERVAL_S,
    LiquipediaCrosshairAdapter,
)
from app.scraper.importer import ImportStatus, import_records, summarize
from app.scraper.scraper_base import (
    FetchResult,
    PoliteHttpClient,
    ScrapeCancelled,
    ScraperError,
    build_user_agent,
)
from app.scraper.scraper_settings import cache_dir, load_contact, save_contact
from app.i18n import display, set_tr_text, tr
from app.ui.components import Banner, label, primary_button
from app.utils.logging import get_logger

log = get_logger("ui.source_update")


class FetchWorker(QThread):
    """Runs the network fetch off the UI thread. It never touches the database."""

    progress = Signal(str)
    succeeded = Signal(object)  # FetchResult
    failed = Signal(str)

    def __init__(self, adapter: LiquipediaCrosshairAdapter, parent=None) -> None:
        super().__init__(parent)
        self.adapter = adapter
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = self.adapter.fetch(self.progress.emit, lambda: self._cancel)
        except ScrapeCancelled as exc:
            self.failed.emit(str(exc))
        except ScraperError as exc:
            log.warning("source_fetch_failed error=%s", exc)
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - never let a thread die silently
            log.exception("source_fetch_crashed")
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.succeeded.emit(result)


class LiquipediaUpdateDialog(QDialog):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.worker: FetchWorker | None = None
        self.setWindowTitle(tr("Update crosshair database from Liquipedia"))
        self.resize(760, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = label("", "mutedLabel", wrap=True)
        set_tr_text(
            intro,
            "Reads VALORANT crosshair share codes from Liquipedia player pages through the "
            "official MediaWiki API, following Liquipedia's API terms: at most one request "
            "every {interval} s, an identifying User-Agent with your contact, and cached "
            "responses (re-used for {days} days). Content is licensed {license}; every record "
            "keeps a permalink for attribution. Existing records are never overwritten; "
            "duplicates are skipped.",
            interval=format(LIQUIPEDIA_MIN_INTERVAL_S, "g"),
            days=LIQUIPEDIA_CACHE_TTL_S // 86400,
            license=LIQUIPEDIA_LICENSE,
        )
        layout.addWidget(intro)
        form = QFormLayout()
        self.contact_edit = QLineEdit(load_contact(context.settings.data_dir))
        self.contact_edit.setPlaceholderText(tr("e-mail or project URL (sent in the User-Agent)"))
        form.addRow(tr("Contact"), self.contact_edit)
        self.force_check = QCheckBox(tr("Ignore cache and re-download"))
        form.addRow("", self.force_check)
        layout.addLayout(form)

        self.banner = Banner()
        layout.addWidget(self.banner)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.start_button = primary_button("Start update")
        self.buttons.addButton(self.start_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.start_button.clicked.connect(self._start)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _start(self) -> None:
        try:
            user_agent = build_user_agent(self.contact_edit.text())
        except ScraperError as exc:
            self.banner.show_message(str(exc), Banner.Kind.ERROR)
            self.contact_edit.setFocus()
            return
        save_contact(self.context.settings.data_dir, self.contact_edit.text())
        client = PoliteHttpClient(
            user_agent=user_agent,
            cache_dir=cache_dir(self.context.settings.data_dir, "liquipedia"),
            min_interval_s=LIQUIPEDIA_MIN_INTERVAL_S,
            cache_ttl_s=LIQUIPEDIA_CACHE_TTL_S,
            force_refresh=self.force_check.isChecked(),
        )
        self.worker = FetchWorker(LiquipediaCrosshairAdapter(client), self)
        self.worker.progress.connect(self.log_view.appendPlainText)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failure)
        self.worker.finished.connect(self._on_finished)
        self.start_button.setEnabled(False)
        self.banner.show_message("Updating… (this takes a few seconds per request)", Banner.Kind.INFO)
        self.log_view.appendPlainText(f"User-Agent: {user_agent}")
        self.worker.start()

    def _on_success(self, result: FetchResult) -> None:
        outcomes = import_records(self.context.repository, result.records,
                                  self.context.research.parameter_ranges)
        counts = summarize(outcomes)
        for o in outcomes:
            if o.status in (ImportStatus.IMPORTED, ImportStatus.SOURCE_ONLY, ImportStatus.INVALID):
                fidelity = f" [{display(o.fidelity)}]" if o.fidelity else ""
                self.log_view.appendPlainText(f"{o.player}: {display(o.status)}{fidelity}")
                for message in o.messages:
                    self.log_view.appendPlainText(f"    - {message}")
        if result.skipped:
            self.log_view.appendPlainText("\n" + tr("Skipped pages:"))
            for note in result.skipped:
                self.log_view.appendPlainText(f"    - {note}")
        self.banner.show_message(
            "{imported} new candidates, {source_only} stored as source only, "
            "{duplicates} already stored, {invalid} invalid codes, {skipped} pages skipped.",
            Banner.Kind.SUCCESS if not counts[ImportStatus.INVALID] else Banner.Kind.WARNING,
            imported=counts[ImportStatus.IMPORTED],
            source_only=counts[ImportStatus.SOURCE_ONLY],
            duplicates=counts[ImportStatus.DUPLICATE],
            invalid=counts[ImportStatus.INVALID],
            skipped=len(result.skipped),
        )
        self.context.signals.data_changed.emit()

    def _on_failure(self, message: str) -> None:
        self.banner.show_message(
            "Update stopped: {message} Nothing was imported.", Banner.Kind.ERROR, message=message
        )

    def _on_finished(self) -> None:
        self.start_button.setEnabled(True)

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(10_000)
        super().reject()
