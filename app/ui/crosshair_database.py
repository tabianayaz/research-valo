"""Crosshair candidate database view and VALORANT code import dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.app_context import AppContext
from app.crosshair.config import CrosshairConfig
from app.data.models import SourceListing
from app.i18n import display, set_tr_text, tr
from app.scraper.importer import ImportOutcome, ImportStatus, Provenance, import_valorant_codes
from app.scraper.parsers import CrosshairCodeError, parse_valorant_code, resolve_primary
from app.ui.components import Banner, Card, label, primary_button, secondary_button
from app.ui.crosshair_widgets import THUMBNAIL_SIZE, thumbnail
from app.ui.source_update_dialog import LiquipediaUpdateDialog
from app.utils.logging import get_logger

log = get_logger("ui.crosshair_database")

COLUMNS = ["Original", "Research model", "Fidelity", "Source", "Player", "Share code"]
FILTERS = [("All", None), ("Exact", "exact"), ("Approximate", "approximate"),
           ("Not representable", "not_representable")]


def listing_fidelity(listing: SourceListing) -> str:
    payload = listing.source.raw_payload or {}
    return str(payload.get("mapping", {}).get("fidelity", "unknown"))


def listing_messages(listing: SourceListing) -> list[str]:
    payload = listing.source.raw_payload or {}
    mapping = payload.get("mapping", {})
    return (
        [tr("Parse: {text}", text=w) for w in payload.get("parsed", {}).get("warnings", [])]
        + [tr("Resolve: {text}", text=w) for w in payload.get("resolve_warnings", [])]
        + [tr("Difference: {text}", text=d) for d in mapping.get("differences", [])]
        + [tr("Info: {text}", text=i) for i in mapping.get("information", [])]
    )


class ImportDialog(QDialog):
    """Paste VALORANT share codes (one per line) and record their provenance."""

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.outcomes: list[ImportOutcome] = []
        self.setWindowTitle(tr("Import VALORANT crosshair codes"))
        self.resize(760, 620)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(label(
            "Provenance is stored with every code. Only enter publicly available player "
            "names. The importer stores candidate data; it does not make recommendations.",
            "mutedLabel", wrap=True,
        ))
        form = QFormLayout()
        self.source_name = QLineEdit("Researcher-provided list")  # stored provenance value: kept English
        self.source_url = QLineEdit()
        self.source_url.setPlaceholderText(tr("Optional, e.g. the page the codes came from"))
        self.source_player = QLineEdit()
        self.source_player.setPlaceholderText(tr("Optional, applies to every code below"))
        form.addRow(tr("Source name"), self.source_name)
        form.addRow(tr("Source URL"), self.source_url)
        form.addRow(tr("Player (public)"), self.source_player)
        layout.addLayout(form)

        layout.addWidget(label(
            "One entry per line: CODE  or  PLAYER, CODE  or  PLAYER, CODE, URL "
            "(comma or tab separated). Per-line player/URL override the fields above.",
            "faintLabel", wrap=True,
        ))
        self.codes = QPlainTextEdit()
        self.codes.setPlaceholderText(
            "0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0\n"
            "aspas, 0;P;h;0;0l;4;0o;0;0a;1;0f;0;1b;0, https://example.org/source\n…"
        )
        layout.addWidget(self.codes, 2)
        load_file = secondary_button("Load from text file…")
        load_file.clicked.connect(self._load_file)
        layout.addWidget(load_file, 0, Qt.AlignmentFlag.AlignLeft)

        self.banner = Banner()
        layout.addWidget(self.banner)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.hide()
        layout.addWidget(self.report, 2)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.import_button = primary_button("Import")
        buttons.addButton(self.import_button, QDialogButtonBox.ButtonRole.ActionRole)
        self.import_button.clicked.connect(self._run_import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Open codes"), "", tr("Text files (*.txt);;All files (*)")
        )
        if path:
            self.codes.setPlainText(Path(path).read_text(encoding="utf-8"))

    def _run_import(self) -> None:
        name = self.source_name.text().strip()
        if not name:
            self.banner.show_message("Source name is required.", Banner.Kind.ERROR)
            return
        provenance = Provenance(
            source_name=name,
            source_url=self.source_url.text().strip() or None,
            source_player=self.source_player.text().strip() or None,
        )
        try:
            self.outcomes = import_valorant_codes(
                self.context.repository, self.codes.toPlainText().splitlines(), provenance,
                self.context.research.parameter_ranges,
            )
        except Exception as exc:  # noqa: BLE001 - report instead of crashing the dialog
            log.exception("import_failed")
            self.banner.show_message("Import failed: {error}", Banner.Kind.ERROR, error=exc)
            return
        counts = {s: sum(o.status == s for o in self.outcomes) for s in ImportStatus}
        self.banner.show_message(
            "Imported {imported} as candidates, {source_only} stored as source only "
            "(not representable), {duplicates} duplicates skipped, {invalid} invalid.",
            Banner.Kind.SUCCESS if not counts[ImportStatus.INVALID] else Banner.Kind.WARNING,
            imported=counts[ImportStatus.IMPORTED],
            source_only=counts[ImportStatus.SOURCE_ONLY],
            duplicates=counts[ImportStatus.DUPLICATE],
            invalid=counts[ImportStatus.INVALID],
        )
        lines = []
        for o in self.outcomes:
            fidelity = f" [{display(o.fidelity)}]" if o.fidelity else ""
            who = f" ({o.player})" if o.player else ""
            lines.append(tr("line {number}", number=o.line_number) + f"{who}: {display(o.status)}{fidelity}")
            lines.extend(f"    - {m}" for m in o.messages)
        self.report.setPlainText("\n".join(lines))
        self.report.show()
        self.context.signals.data_changed.emit()


class CrosshairDatabaseView(QWidget):
    crosshair_selected = Signal(int)  # crosshair_id to open in the editor

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.listings: list[SourceListing] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(label(
            "Publicly collected or manually provided crosshair configurations. This source "
            "data is stored separately from measurement data. 'Original' renders the static "
            "VALORANT crosshair; 'Research model' renders what the experiment would use.",
            "mutedLabel", wrap=True,
        ))

        toolbar = QHBoxLayout()
        import_button = primary_button("Import VALORANT codes…")
        import_button.clicked.connect(self._open_import)
        update_button = secondary_button("Update from Liquipedia…")
        update_button.setToolTip(tr("Manual update through the Liquipedia API (never automatic)"))
        update_button.clicked.connect(self._open_update)
        self.filter_combo = QComboBox()
        for text, value in FILTERS:
            self.filter_combo.addItem(tr(text), value)
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        self.open_button = secondary_button("Open in editor")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        self.count_label = label("", "faintLabel")
        toolbar.addWidget(import_button)
        toolbar.addWidget(update_button)
        toolbar.addWidget(QLabel(tr("Fidelity")))
        toolbar.addWidget(self.filter_combo)
        toolbar.addWidget(self.open_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.count_label)
        layout.addLayout(toolbar)

        self.empty_label = label(
            "No crosshair sources yet. Use 'Import VALORANT codes…' to add candidates.",
            "mutedLabel", wrap=True,
        )
        layout.addWidget(self.empty_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(THUMBNAIL_SIZE.height() + 8)
        header = self.table.horizontalHeader()
        for column in range(len(COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(420)
        self.table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.table, 1)

        details = Card("Details")
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(110)
        self.details.setMaximumHeight(160)
        self.details.setPlaceholderText(tr("Select a row to see mapping differences and warnings."))
        details.body.addWidget(self.details)
        layout.addWidget(details)

    def refresh(self) -> None:
        wanted = self.filter_combo.currentData()
        all_listings = self.context.repository.list_source_listings()
        self.listings = [l for l in all_listings if wanted is None or listing_fidelity(l) == wanted]
        self.table.setRowCount(len(self.listings))
        dpr = self.devicePixelRatioF()
        for row, listing in enumerate(self.listings):
            self._set_thumbnail(row, 0, self._original_shape(listing), dpr)
            research_shape = (
                CrosshairConfig.from_record(listing.crosshair).to_shape()
                if listing.crosshair else None
            )
            self._set_thumbnail(row, 1, research_shape, dpr)
            for column, text in (
                (2, display(listing_fidelity(listing).replace("_", " "))),
                (3, listing.source.source_name),
                (4, listing.source.source_player or "–"),
                (5, listing.source.source_code or ""),
            ):
                item = QTableWidgetItem(text)
                if column == 5:
                    item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.empty_label.setVisible(not all_listings)
        set_tr_text(
            self.count_label,
            "{shown} shown · {usable} usable as candidates · {total} sources total",
            shown=len(self.listings),
            usable=sum(1 for l in all_listings if l.crosshair),
            total=len(all_listings),
        )
        self.details.clear()
        self.open_button.setEnabled(False)

    def _original_shape(self, listing: SourceListing):
        if not listing.source.source_code:
            return None
        try:
            return resolve_primary(parse_valorant_code(listing.source.source_code)).to_shape()
        except CrosshairCodeError:
            return None

    def _set_thumbnail(self, row: int, column: int, shape, dpr: float) -> None:
        pixmap = thumbnail(shape, self.context.research, dpr)
        cell = QLabel()
        cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap is None:
            cell.setText("—")
            cell.setToolTip(tr("Not representable in the research model"))
        else:
            cell.setPixmap(pixmap)
        self.table.setCellWidget(row, column, cell)

    def _selected_listing(self) -> SourceListing | None:
        rows = self.table.selectionModel().selectedRows()
        return self.listings[rows[0].row()] if rows else None

    def _on_selection(self) -> None:
        listing = self._selected_listing()
        if listing is None:
            return
        self.open_button.setEnabled(listing.crosshair is not None)
        record_info = (listing.source.raw_payload or {}).get("source_record", {})
        extra = record_info.get("extra", {})
        lines = [
            tr("Source: {name}", name=listing.source.source_name)
            + (f" ({listing.source.source_url})" if listing.source.source_url else ""),
            tr("Retrieved: {when}", when=listing.source.retrieved_at)
            + (tr(" · published date: {date}", date=record_info["source_date"])
               if record_info.get("source_date") else ""),
        ]
        if extra.get("license"):
            lines.append(tr("License: {license} · Attribution: {attribution}",
                            license=extra["license"], attribution=extra.get("attribution", "")))
        lines += [
            tr("Code: {code}", code=listing.source.source_code),
            tr("Fidelity: {fidelity}", fidelity=display(listing_fidelity(listing))),
        ]
        if listing.crosshair:
            c = CrosshairConfig.from_record(listing.crosshair)
            outline = (tr("on {value}", value=format(c.outline_thickness, "g"))
                       if c.outline_enabled else tr("off"))
            lines.append(tr(
                "Research model: color {color}, size {size}, thickness {thickness}, "
                "gap {gap}, outline {outline}, opacity {opacity}",
                color=c.color, size=format(c.size, "g"), thickness=format(c.thickness, "g"),
                gap=format(c.gap, "g"), outline=outline, opacity=format(c.opacity, "g"),
            ))
        lines += [""] + (listing_messages(listing) or [tr("No differences or warnings.")])
        self.details.setPlainText("\n".join(lines))

    def _open_selected(self) -> None:
        listing = self._selected_listing()
        if listing and listing.crosshair:
            self.crosshair_selected.emit(listing.crosshair.crosshair_id)

    def _open_import(self) -> None:
        dialog = ImportDialog(self.context, self)
        dialog.exec()
        self.refresh()

    def _open_update(self) -> None:
        dialog = LiquipediaUpdateDialog(self.context, self)
        dialog.exec()
        self.refresh()
