"""Persisted, non-research scraper settings (contact for the User-Agent)."""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE = "scraper_settings.json"


def load_contact(data_dir: Path) -> str:
    path = data_dir / SETTINGS_FILE
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("contact", ""))
    except (OSError, ValueError):
        return ""


def save_contact(data_dir: Path, contact: str) -> None:
    path = data_dir / SETTINGS_FILE
    path.write_text(json.dumps({"contact": contact.strip()}, indent=2), encoding="utf-8")


def cache_dir(data_dir: Path, source: str) -> Path:
    return data_dir / "raw" / "scraper_cache" / source
