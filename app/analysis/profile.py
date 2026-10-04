"""Player profile (Milestone 7): the player's own baseline metrics per task.

Source rule (placeholder, see README "Research decisions"): for each task the
latest *completed* baseline session of the player is used. Aborted sessions
and candidate sessions are never used. Metrics are recomputed from raw data
and never include practice or invalid (pre-target movement) trials.
The profile is descriptive; it does not compare the player with other people.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.analysis.metrics import ANALYSIS_VERSION, TASK_METRICS, analyze_session
from app.data.models import AssessmentStage, Condition, ExperimentType, SessionStatus
from app.data.repository import Repository

PROFILE_RULE = "latest completed baseline session per task"


@dataclass
class TaskProfile:
    task: ExperimentType
    session_id: int
    started_at: str
    metrics: dict[str, float | None]
    protocol_version: str | None = None


@dataclass
class PlayerProfile:
    player_id: str
    tasks: dict[ExperimentType, TaskProfile] = field(default_factory=dict)

    @property
    def missing_tasks(self) -> list[ExperimentType]:
        return [t for t in ExperimentType if t not in self.tasks]

    @property
    def source_session_ids(self) -> list[int]:
        return [p.session_id for p in self.tasks.values()]

    def value(self, key: str) -> float | None:
        """Look up ``"<task>.<metric>"``, e.g. ``"flick.error_ratio_mean"``."""
        task, _, metric = key.partition(".")
        profile = self.tasks.get(ExperimentType(task))
        return profile.metrics.get(metric) if profile else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "rule": PROFILE_RULE,
            "analysis_version": ANALYSIS_VERSION,
            "tasks": {
                str(t): {"session_id": p.session_id, "started_at": p.started_at,
                         "protocol_version": p.protocol_version, "metrics": p.metrics}
                for t, p in self.tasks.items()
            },
            "missing_tasks": [str(t) for t in self.missing_tasks],
        }


def build_profile(repo: Repository, player_id: str) -> PlayerProfile:
    profile = PlayerProfile(player_id)
    for task in ExperimentType:
        sessions = repo.list_sessions(player_id, task, Condition.BASELINE, SessionStatus.COMPLETED)
        sessions = [
            session for session in sessions
            if session.assessment_stage != AssessmentStage.PRACTICE
        ]
        if not sessions:
            continue
        latest = sessions[0]
        analysis = analyze_session(repo, latest.session_id)
        profile.tasks[task] = TaskProfile(
            task=task,
            session_id=latest.session_id,
            started_at=latest.started_at,
            metrics={name: analysis.metrics.get(name) for name in TASK_METRICS[task]},
            protocol_version=latest.protocol_version,
        )
    return profile
