"""Application-level settings (paths, UI constants).

Research parameters (baseline crosshair, task parameters, recommendation
weights) are deliberately NOT defined here. They will live in dedicated,
versioned configuration so that each session can record exactly which
parameters were active.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

APP_NAME = "Crosshair Research"
APP_TITLE_JA = "FPS初級者の照準操作支援を目的としたプレイデータ分析に基づくクロスヘア推薦システム"
APP_TITLE_EN = "Crosshair Recommendation System Based on Player Aiming Data"

DB_PATH_ENV = "CROSSHAIR_RESEARCH_DB"
DATA_DIR_ENV = "CROSSHAIR_RESEARCH_DATA_DIR"


@dataclass(frozen=True)
class AppSettings:
    """Resolved filesystem locations used by the application."""

    data_dir: Path
    db_path: Path
    exports_dir: Path = field(init=False)
    raw_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "exports_dir", self.data_dir / "exports")
        object.__setattr__(self, "raw_dir", self.data_dir / "raw")
        object.__setattr__(self, "logs_dir", self.data_dir / "logs")

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.exports_dir, self.raw_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings(data_dir: Path | None = None, db_path: Path | None = None) -> AppSettings:
    """Build settings, honouring explicit arguments, then env vars, then defaults."""
    resolved_data_dir = data_dir or Path(os.environ.get(DATA_DIR_ENV, PROJECT_ROOT / "data"))
    resolved_db_path = db_path or Path(os.environ.get(DB_PATH_ENV, resolved_data_dir / "app.db"))
    return AppSettings(data_dir=Path(resolved_data_dir), db_path=Path(resolved_db_path))
