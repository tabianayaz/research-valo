"""CSV / JSON export of raw and derived session data.

Exports are written to new timestamped folders under ``data/exports`` and
never modify the database.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.analysis.metrics import ANALYSIS_VERSION, METRICS, SessionAnalysis
from app.data.repository import Repository
from app.utils.timing import utc_now_iso

TRIAL_COLUMNS = [
    "trial_id", "trial_number", "task_type", "result", "target_id", "previous_target_id",
    "target_x", "target_y", "target_size", "target_distance", "target_speed",
    "initial_crosshair_x", "initial_crosshair_y", "reaction_time_ms", "movement_time_ms",
    "completion_time_ms", "error_distance", "movement_distance", "recorded_at",
    "trial_status", "timing_quality", "trial_phase",
]
VALIDITY_COLUMNS = ["effective_status", "moving_at_onset", "valid_for_reaction_time",
                    "valid_for_completion_time", "valid_for_accuracy", "valid_for_tracking"]
SESSION_ORDER_COLUMNS = [
    "participant_id", "session_id", "task_order_group", "task_order",
    "task_position", "assessment_stage",
]


def _stamp() -> str:
    return utc_now_iso()[:19].replace(":", "").replace("-", "")


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def export_session(repo: Repository, analysis: SessionAnalysis, exports_dir: Path) -> Path:
    """Write trials.csv, samples.csv, events.csv and session.json for one session."""
    session = analysis.session
    folder = exports_dir / f"session_{session.session_id}_{session.experiment_type}_{_stamp()}"
    folder.mkdir(parents=True, exist_ok=False)

    trials = repo.list_trials(session.session_id)
    rows_by_id = {r.trial.trial_id: r for r in analysis.rows}
    order_values = [
        session.player_id,
        session.session_id,
        session.task_order_group,
        json.dumps(session.task_order) if session.task_order else "",
        session.task_position,
        session.assessment_stage,
    ]

    def validity(trial) -> list[Any]:
        row = rows_by_id.get(trial.trial_id)
        if row is None:
            return [""] * len(VALIDITY_COLUMNS)
        return [row.status, row.moving_at_onset, *[getattr(row, c) for c in VALIDITY_COLUMNS[2:]]]

    _write_csv(
        folder / "trials.csv",
        [*SESSION_ORDER_COLUMNS, *TRIAL_COLUMNS, *VALIDITY_COLUMNS, "extra_json"],
        [[*order_values, *[getattr(t, c) for c in TRIAL_COLUMNS], *validity(t),
          json.dumps(t.extra, sort_keys=True) if t.extra else ""] for t in trials],
    )
    sample_rows, event_rows = [], []
    for t in trials:
        for s in repo.list_samples(t.trial_id):
            sample_rows.append([*order_values, t.trial_id, t.trial_number, s.t_ms, s.cursor_x, s.cursor_y,
                                s.target_x, s.target_y, s.on_target])
        for e in repo.list_events(t.trial_id):
            event_rows.append([*order_values, t.trial_id, t.trial_number, e.t_ms,
                               e.event_type, e.x, e.y, e.is_hit])
    _write_csv(folder / "samples.csv",
               [*SESSION_ORDER_COLUMNS, "trial_id", "trial_number", "t_ms", "cursor_x",
                "cursor_y", "target_x", "target_y", "on_target"],
               sample_rows)
    _write_csv(folder / "events.csv",
               [*SESSION_ORDER_COLUMNS, "trial_id", "trial_number", "t_ms", "event_type",
                "x", "y", "is_hit"], event_rows)

    crosshair = repo.get_crosshair(session.crosshair_id)
    payload = {
        "exported_at": utc_now_iso(),
        "analysis_version": ANALYSIS_VERSION,
        "session": asdict(session),
        "task_order_metadata": dict(zip(SESSION_ORDER_COLUMNS, order_values)),
        "crosshair": asdict(crosshair) if crosshair else None,
        "metrics": {
            name: {"value": value, "unit": METRICS[name].unit, "label": METRICS[name].label}
            for name, value in analysis.metrics.items()
        },
        "recomputation_mismatches": analysis.mismatches,
    }
    (folder / "session.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return folder


def export_rows(path_dir: Path, name: str, header: list[str], rows: list[list[Any]]) -> Path:
    """Write a single CSV (used by the comparison screen)."""
    path_dir.mkdir(parents=True, exist_ok=True)
    path = path_dir / f"{name}_{_stamp()}.csv"
    _write_csv(path, header, rows)
    return path
