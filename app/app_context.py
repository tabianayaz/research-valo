"""Shared application state passed explicitly to UI pages (no globals)."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from app.config.research import ResearchParameters
from app.config.settings import AppSettings
from app.data.database import Database
from app.data.models import CrosshairRecord, Player
from app.data.repository import Repository


class ContextSignals(QObject):
    player_changed = Signal(object)  # Player | None
    data_changed = Signal()


@dataclass
class AppContext:
    settings: AppSettings
    database: Database
    repository: Repository
    research: ResearchParameters
    baseline_crosshair: CrosshairRecord
    current_player: Player | None = None
    signals: ContextSignals = field(default_factory=ContextSignals)

    def set_current_player(self, player: Player | None) -> None:
        self.current_player = player
        self.signals.player_changed.emit(player)
