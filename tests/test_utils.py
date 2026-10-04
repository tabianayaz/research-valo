from __future__ import annotations

from pathlib import Path

from app.config.settings import load_settings
from app.utils.timing import Stopwatch, utc_now_iso


def test_stopwatch_is_monotonic() -> None:
    watch = Stopwatch()
    assert watch.elapsed_ms == 0.0
    watch.start()
    assert watch.running
    elapsed = watch.stop()
    assert elapsed >= 0.0
    assert not watch.running
    assert watch.elapsed_ms == elapsed


def test_utc_timestamp_has_timezone() -> None:
    assert utc_now_iso().endswith("+00:00")


def test_settings_paths(tmp_path: Path) -> None:
    settings = load_settings(data_dir=tmp_path)
    settings.ensure_directories()
    assert settings.db_path == tmp_path / "app.db"
    for directory in (settings.exports_dir, settings.raw_dir, settings.logs_dir):
        assert directory.is_dir()
