"""Human-readable labels for sessions (shared by Results, Comparison and History)."""

from __future__ import annotations

from app.data.models import Session
from app.i18n import display, tr

TASK_LABELS = {"flick": "Flick Aim", "tracking": "Tracking", "switching": "Target Switching"}


def task_label(task: object) -> str:
    """Translated display name of a task (stored value stays the enum code)."""
    return tr(TASK_LABELS.get(str(task), str(task)))


def task_order_text(values) -> str:
    """Translated "A → B → C" text for a stored task order."""
    from app.experiment.task_order import parse_task_order

    return " → ".join(task_label(task) for task in parse_task_order(values))


def session_label(session: Session, crosshair_name: str | None = None) -> str:
    started = (session.started_at or "")[:16].replace("T", " ")
    parts = [
        f"#{session.session_id}",
        tr(TASK_LABELS.get(str(session.experiment_type), str(session.experiment_type))),
        display(session.condition),
        session.player_id,
        started,
    ]
    if crosshair_name:
        parts.append(crosshair_name)
    if str(session.status) != "completed":
        parts.append(f"[{display(session.status)}]")
    return "  ·  ".join(parts)
