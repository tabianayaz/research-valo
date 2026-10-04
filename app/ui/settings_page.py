"""Settings / about: storage locations and versions."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFormLayout, QWidget

from app import __version__
from app.app_context import AppContext
from app.ui.components import BasePage, Card, hbox, label, secondary_button


class SettingsPage(BasePage):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__("Settings", "Storage locations and software versions.", parent)
        self.context = context
        settings = context.settings

        storage = Card("Storage")
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.addRow("Database", label(str(settings.db_path)))
        form.addRow("Exports", label(str(settings.exports_dir)))
        form.addRow("Raw data", label(str(settings.raw_dir)))
        form.addRow("Logs", label(str(settings.logs_dir)))
        storage.body.addLayout(form)
        open_button = secondary_button("Open data folder")
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(settings.data_dir)))
        )
        storage.body.addLayout(hbox(open_button))
        self.content.addWidget(storage)

        versions = Card("Versions")
        version_form = QFormLayout()
        version_form.setHorizontalSpacing(18)
        version_form.addRow("Application", label(__version__))
        version_form.addRow("Database schema", label(str(context.database.schema_version())))
        version_form.addRow("Python", label(platform.python_version()))
        version_form.addRow("PySide6", label(PySide6.__version__))
        versions.body.addLayout(version_form)
        self.content.addWidget(versions)
        self.finish_layout()
