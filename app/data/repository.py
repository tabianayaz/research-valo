"""Repository: the only place that issues SQL for domain objects.

UI and experiment code talk to this class instead of writing SQL, which keeps
the storage format changeable without touching the rest of the system.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable

from app.data.database import Database
from app.data.models import (
    NON_ANALYSED_STAGES,
    AssessmentStage,
    AssessmentStatus,
    Condition,
    ConditionEvaluation,
    CrosshairRecord,
    EvaluationStatus,
    CrosshairRole,
    CrosshairSource,
    Environment,
    ExperimentType,
    ImportMethod,
    Player,
    Session,
    SessionStatus,
    SessionSummary,
    SourceListing,
    TaskAssessment,
    TaskOrderMode,
    Trial,
    TrialEvent,
    TimingQuality,
    TrialPhase,
    TrialResult,
    TrialSample,
    TrialStatus,
)
from app.experiment.conditions import (
    ConditionOrderAssignment,
    condition_order_for_sequence,
    validate_condition_order,
)
from app.experiment.task_order import assignment_for_sequence, validate_assignment
from app.utils.logging import get_logger
from app.utils.timing import utc_now_iso

log = get_logger("repository")


class RepositoryError(RuntimeError):
    """Raised when a persistence operation violates an invariant."""


def crosshair_config_hash(record: CrosshairRecord) -> str:
    payload = json.dumps(record.parameter_dict(), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Repository:
    def __init__(self, database: Database) -> None:
        self.db = database

    @property
    def _conn(self) -> sqlite3.Connection:
        return self.db.connection

    # ------------------------------------------------------------------ players
    def save_player(self, player: Player) -> Player:
        """Insert a new player or update an existing player's profile fields.

        Player profile fields are descriptive metadata, not raw measurement
        data. The per-session hardware state is additionally snapshotted in
        ``environments`` so changing a profile never alters past sessions.
        """
        player.validate()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            existing = conn.execute(
                """SELECT created_at, task_order_sequence, task_order_group, task_order_json
                   FROM players WHERE player_id = ?""",
                (player.player_id,),
            ).fetchone()
            if existing is None:
                sequence = int(conn.execute(
                    "SELECT COALESCE(MAX(task_order_sequence), 0) + 1 AS sequence FROM players"
                ).fetchone()["sequence"])
                assignment = assignment_for_sequence(sequence)
                conn.execute(
                    """INSERT INTO players (player_id, created_at, updated_at, fps_experience,
                           aim_training_frequency, mouse_dpi, sensitivity, edpi,
                           display_width, display_height, notes, task_order_sequence,
                           task_order_group, task_order_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        player.player_id, now, now, player.fps_experience,
                        player.aim_training_frequency, player.mouse_dpi, player.sensitivity,
                        player.edpi, player.display_width, player.display_height, player.notes,
                        assignment.sequence, assignment.group,
                        json.dumps(assignment.values),
                    ),
                )
                player.created_at = now
                player.task_order_sequence = assignment.sequence
                player.task_order_group = assignment.group
                player.task_order = assignment.values
                log.info("player_created player_id=%s", player.player_id)
            else:
                if existing["task_order_group"] is None:
                    sequence = int(conn.execute(
                        "SELECT COALESCE(MAX(task_order_sequence), 0) + 1 AS sequence FROM players"
                    ).fetchone()["sequence"])
                    assignment = assignment_for_sequence(sequence)
                    conn.execute(
                        """UPDATE players SET task_order_sequence = ?, task_order_group = ?,
                               task_order_json = ? WHERE player_id = ?""",
                        (assignment.sequence, assignment.group, json.dumps(assignment.values),
                         player.player_id),
                    )
                else:
                    assignment = assignment_for_sequence(int(existing["task_order_sequence"]))
                    stored_order = tuple(json.loads(existing["task_order_json"]))
                    validate_assignment(str(existing["task_order_group"]), stored_order)
                    assignment = type(assignment)(
                        int(existing["task_order_sequence"]), str(existing["task_order_group"]),
                        tuple(ExperimentType(value) for value in stored_order),
                    )
                if player.task_order_group is not None and (
                    player.task_order_group != assignment.group
                    or tuple(player.task_order or ()) != assignment.values
                ):
                    raise RepositoryError("A participant's stored task-order assignment cannot be changed")
                conn.execute(
                    """UPDATE players SET updated_at = ?, fps_experience = ?,
                           aim_training_frequency = ?, mouse_dpi = ?, sensitivity = ?, edpi = ?,
                           display_width = ?, display_height = ?, notes = ?
                       WHERE player_id = ?""",
                    (
                        now, player.fps_experience, player.aim_training_frequency,
                        player.mouse_dpi, player.sensitivity, player.edpi,
                        player.display_width, player.display_height, player.notes,
                        player.player_id,
                    ),
                )
                player.created_at = existing["created_at"]
                player.task_order_sequence = assignment.sequence
                player.task_order_group = assignment.group
                player.task_order = assignment.values
                log.info("player_updated player_id=%s", player.player_id)
            condition = self._ensure_condition_order(conn, player.player_id, player.task_order_sequence)
            if player.condition_order_group is not None and (
                player.condition_order_group != condition.group
                or tuple(player.condition_order or ()) != condition.values
            ):
                raise RepositoryError("A participant's stored condition-order assignment cannot be changed")
            player.condition_order_group = condition.group
            player.condition_order = condition.values
            player.condition_assignment_method = condition.method
        player.updated_at = now
        return player

    @staticmethod
    def _ensure_condition_order(conn: sqlite3.Connection, player_id: str, sequence: int):
        """Return the stored CS/SC assignment, assigning it once from the participant sequence."""
        row = conn.execute(
            """SELECT condition_order_group, condition_order_json, condition_assignment_method
               FROM players WHERE player_id = ?""",
            (player_id,),
        ).fetchone()
        if row["condition_order_group"] is not None:
            order = validate_condition_order(row["condition_order_group"],
                                             json.loads(row["condition_order_json"]))
            return ConditionOrderAssignment(row["condition_order_group"], order,  # type: ignore[arg-type]
                                            row["condition_assignment_method"])
        assignment = condition_order_for_sequence(sequence)
        conn.execute(
            """UPDATE players SET condition_order_group = ?, condition_order_json = ?,
                   condition_assignment_method = ? WHERE player_id = ?""",
            (assignment.group, json.dumps(assignment.values), assignment.method, player_id),
        )
        log.info("condition_order_assigned player_id=%s group=%s", player_id, assignment.group)
        return assignment

    def get_player(self, player_id: str) -> Player | None:
        row = self._conn.execute(
            "SELECT * FROM players WHERE player_id = ?", (player_id,)
        ).fetchone()
        return self._row_to_player(row) if row else None

    def list_players(self) -> list[Player]:
        rows = self._conn.execute("SELECT * FROM players ORDER BY created_at").fetchall()
        return [self._row_to_player(row) for row in rows]

    @staticmethod
    def _row_to_player(row: sqlite3.Row) -> Player:
        data = dict(row)
        raw_order = data.pop("task_order_json", None)
        raw_conditions = data.pop("condition_order_json", None)
        return Player(**data, task_order=tuple(json.loads(raw_order)) if raw_order else None,
                      condition_order=tuple(json.loads(raw_conditions)) if raw_conditions else None)

    # --------------------------------------------------------------- crosshairs
    def add_crosshair(self, record: CrosshairRecord) -> CrosshairRecord:
        with self.db.transaction() as conn:
            self._insert_crosshair(conn, record)
        return record

    @staticmethod
    def _insert_crosshair(conn: sqlite3.Connection, record: CrosshairRecord) -> None:
        now = utc_now_iso()
        cursor = conn.execute(
            """INSERT INTO crosshairs (name, role, color, size, thickness, gap,
                   outline_enabled, outline_thickness, opacity, config_hash,
                   source_id, fidelity, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.name, CrosshairRole(record.role).value, record.color, record.size,
                record.thickness, record.gap, int(record.outline_enabled),
                record.outline_thickness, record.opacity, crosshair_config_hash(record),
                record.source_id, record.fidelity, now,
            ),
        )
        record.crosshair_id = cursor.lastrowid
        record.created_at = now

    def find_crosshair_by_hash(
        self, config_hash: str, role: CrosshairRole
    ) -> CrosshairRecord | None:
        row = self._conn.execute(
            "SELECT * FROM crosshairs WHERE config_hash = ? AND role = ? "
            "ORDER BY crosshair_id LIMIT 1",
            (config_hash, CrosshairRole(role).value),
        ).fetchone()
        return self._row_to_crosshair(row) if row else None

    # -------------------------------------------------------- crosshair sources
    def add_source_with_crosshair(
        self, source: CrosshairSource, crosshair: CrosshairRecord | None
    ) -> tuple[CrosshairSource, CrosshairRecord | None]:
        """Store provenance and (optionally) the derived crosshair atomically."""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO crosshair_sources (source_name, source_url, source_player,
                       retrieved_at, import_method, raw_payload, notes, source_format,
                       source_code)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source.source_name, source.source_url, source.source_player,
                    source.retrieved_at or now, ImportMethod(source.import_method).value,
                    json.dumps(source.raw_payload, ensure_ascii=False, sort_keys=True)
                    if source.raw_payload is not None else None,
                    source.notes, source.source_format, source.source_code,
                ),
            )
            source.source_id = cursor.lastrowid
            source.retrieved_at = source.retrieved_at or now
            if crosshair is not None:
                crosshair.source_id = source.source_id
                self._insert_crosshair(conn, crosshair)
        log.info(
            "crosshair_source_added source_id=%s format=%s crosshair_id=%s",
            source.source_id, source.source_format,
            crosshair.crosshair_id if crosshair else None,
        )
        return source, crosshair

    def find_source(
        self,
        source_format: str,
        source_code: str,
        source_name: str,
        source_player: str | None,
    ) -> CrosshairSource | None:
        row = self._conn.execute(
            """SELECT * FROM crosshair_sources
               WHERE source_format = ? AND source_code = ? AND source_name = ?
                 AND source_player IS ?""",
            (source_format, source_code, source_name, source_player),
        ).fetchone()
        return self._row_to_source(row) if row else None

    def list_source_listings(self) -> list[SourceListing]:
        sources = self._conn.execute(
            "SELECT * FROM crosshair_sources ORDER BY source_id"
        ).fetchall()
        crosshairs = {
            row["source_id"]: self._row_to_crosshair(row)
            for row in self._conn.execute(
                "SELECT * FROM crosshairs WHERE source_id IS NOT NULL"
            ).fetchall()
        }
        return [
            SourceListing(self._row_to_source(row), crosshairs.get(row["source_id"]))
            for row in sources
        ]

    @staticmethod
    def _row_to_source(row: sqlite3.Row) -> CrosshairSource:
        data = dict(row)
        payload = data.pop("raw_payload")
        data["import_method"] = ImportMethod(data["import_method"])
        return CrosshairSource(**data, raw_payload=json.loads(payload) if payload else None)

    def get_crosshair(self, crosshair_id: int) -> CrosshairRecord | None:
        row = self._conn.execute(
            "SELECT * FROM crosshairs WHERE crosshair_id = ?", (crosshair_id,)
        ).fetchone()
        return self._row_to_crosshair(row) if row else None

    def list_crosshairs(self, role: CrosshairRole | None = None) -> list[CrosshairRecord]:
        if role is None:
            rows = self._conn.execute("SELECT * FROM crosshairs ORDER BY crosshair_id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM crosshairs WHERE role = ? ORDER BY crosshair_id",
                (CrosshairRole(role).value,),
            ).fetchall()
        return [self._row_to_crosshair(row) for row in rows]

    _CROSSHAIR_REFERENCES = (
        ("sessions", "crosshair_id"),
        ("sessions", "selected_candidate_id"),
        ("task_assessments", "crosshair_id"),
        ("recommendation_candidates", "crosshair_id"),
        ("condition_evaluations", "selected_candidate_id"),
        ("condition_evaluations", "standard_crosshair_id"),
    )

    def crosshair_usage(self, crosshair_id: int) -> int:
        """Number of stored rows that reference this crosshair."""
        return sum(
            self._conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (crosshair_id,)
            ).fetchone()[0]
            for table, column in self._CROSSHAIR_REFERENCES
        )

    def delete_custom_crosshair(self, crosshair_id: int) -> None:
        """Delete a user-created crosshair that no research record references.

        Baseline and candidate crosshairs, and custom crosshairs already used by a
        session, assessment, recommendation or evaluation, are never deleted:
        those rows are part of the raw research record.
        """
        record = self.get_crosshair(crosshair_id)
        if record is None:
            raise RepositoryError(f"Crosshair {crosshair_id} does not exist.")
        if record.role != CrosshairRole.CUSTOM:
            raise RepositoryError("Only custom crosshairs can be deleted.")
        if self.crosshair_usage(crosshair_id):
            raise RepositoryError(
                "This crosshair is used by recorded sessions or recommendations and is kept."
            )
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "DELETE FROM crosshairs WHERE crosshair_id = ? AND role = ?",
                    (crosshair_id, CrosshairRole.CUSTOM.value),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryError(
                "This crosshair is used by recorded sessions or recommendations and is kept."
            ) from exc
        log.info("custom_crosshair_deleted crosshair_id=%s name=%s", crosshair_id, record.name)

    @staticmethod
    def _row_to_crosshair(row: sqlite3.Row) -> CrosshairRecord:
        data = dict(row)
        data.pop("config_hash", None)
        data["role"] = CrosshairRole(data["role"])
        data["outline_enabled"] = bool(data["outline_enabled"])
        return CrosshairRecord(**data)

    # ------------------------------------------------------------- environments
    def add_environment(self, env: Environment) -> Environment:
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO environments (created_at, display_width, display_height,
                       app_width, app_height, device_pixel_ratio, refresh_rate_hz,
                       measured_fps, fov, background_color, background_condition,
                       target_color, target_size, target_speed, mouse_dpi, sensitivity,
                       extra_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now, env.display_width, env.display_height, env.app_width, env.app_height,
                    env.device_pixel_ratio, env.refresh_rate_hz, env.measured_fps, env.fov,
                    env.background_color, env.background_condition, env.target_color,
                    env.target_size, env.target_speed, env.mouse_dpi, env.sensitivity,
                    env.extra_json(),
                ),
            )
        env.environment_id = cursor.lastrowid
        env.created_at = now
        return env

    # ------------------------------------------------------ task assessments
    def start_or_resume_task_assessment(
        self,
        player_id: str,
        condition: Condition,
        crosshair_id: int,
        recommendation_id: int | None,
        protocol,
        evaluation_id: int | None = None,
        condition_position: int | None = None,
    ) -> TaskAssessment:
        """Create one controlled three-task run, or return its persisted active state.

        Baseline (and legacy) assessments start with the practice block. Post-baseline
        condition assessments of an evaluation start with the condition
        familiarization block instead (``protocol.condition_familiarization_*``).
        """
        active = self.get_active_task_assessment(player_id)
        if active is not None:
            if (Condition(active.condition), active.crosshair_id, active.recommendation_id,
                    active.evaluation_id, active.condition_position) != (
                Condition(condition), crosshair_id, recommendation_id, evaluation_id, condition_position,
            ):
                raise RepositoryError(
                    "This participant already has an unfinished controlled assessment. "
                    "Resume it before changing the condition or crosshair."
                )
            return self.recover_task_assessment(active.assessment_id)

        player = self.get_player(player_id)
        if player is None:
            raise RepositoryError(f"Unknown player_id {player_id!r}")
        if player.task_order_group is None or player.task_order is None:
            player = self.save_player(player)
        order = tuple(player.task_order)
        practice_order = tuple(protocol.practice_order(order))
        pre_stage = AssessmentStage.FAMILIARIZATION if evaluation_id is not None else AssessmentStage.PRACTICE
        pre_positions = [
            index for index, task in enumerate(practice_order, start=1)
            if protocol.pre_block_count(pre_stage, str(task)) > 0
        ]
        if pre_positions:
            stage = pre_stage
            position = pre_positions[0]
            current_task = ExperimentType(practice_order[position - 1])
        else:
            stage = AssessmentStage.EXPERIMENTAL
            position = 1
            current_task = ExperimentType(order[0])
        assessment = TaskAssessment(
            player_id=player_id,
            condition=Condition(condition),
            crosshair_id=crosshair_id,
            recommendation_id=recommendation_id,
            task_order_group=player.task_order_group,
            task_order=order,
            practice_task_order=practice_order,
            stage=stage,
            current_position=position,
            current_task=current_task,
            completed_tasks={str(pre_stage): [], "experimental": []},
            protocol_version=protocol.version,
            protocol_snapshot=protocol.stored_snapshot(),
            evaluation_id=evaluation_id,
            condition_position=condition_position,
        )
        assessment.validate()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO task_assessments (
                       player_id, started_at, updated_at, condition, crosshair_id,
                       recommendation_id, task_order_group, task_order_json,
                       practice_order_json, stage, current_position, current_task,
                       completed_tasks_json, status, protocol_version, protocol_snapshot_json,
                       evaluation_id, condition_position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    assessment.player_id, now, now, str(assessment.condition),
                    assessment.crosshair_id, assessment.recommendation_id,
                    assessment.task_order_group, json.dumps(assessment.task_order),
                    json.dumps(assessment.practice_task_order), str(assessment.stage),
                    assessment.current_position, str(assessment.current_task),
                    json.dumps(assessment.completed_tasks, sort_keys=True),
                    str(assessment.status), assessment.protocol_version,
                    json.dumps(assessment.protocol_snapshot, sort_keys=True),
                    assessment.evaluation_id, assessment.condition_position,
                ),
            )
        assessment.assessment_id = cursor.lastrowid
        assessment.started_at = now
        assessment.updated_at = now
        log.info(
            "task_assessment_started assessment_id=%s player_id=%s group=%s",
            assessment.assessment_id, player_id, assessment.task_order_group,
        )
        return assessment

    def get_task_assessment(self, assessment_id: int) -> TaskAssessment | None:
        row = self._conn.execute(
            "SELECT * FROM task_assessments WHERE assessment_id = ?", (assessment_id,)
        ).fetchone()
        return self._row_to_task_assessment(row) if row else None

    def get_active_task_assessment(self, player_id: str) -> TaskAssessment | None:
        row = self._conn.execute(
            """SELECT * FROM task_assessments
               WHERE player_id = ? AND status = 'in_progress'
               ORDER BY assessment_id DESC LIMIT 1""",
            (player_id,),
        ).fetchone()
        return self._row_to_task_assessment(row) if row else None

    @staticmethod
    def _row_to_task_assessment(row: sqlite3.Row) -> TaskAssessment:
        data = dict(row)
        data["condition"] = Condition(data["condition"])
        data["task_order"] = tuple(json.loads(data.pop("task_order_json")))
        data["practice_task_order"] = tuple(json.loads(data.pop("practice_order_json")))
        data["stage"] = AssessmentStage(data["stage"])
        data["current_task"] = (
            ExperimentType(data["current_task"]) if data["current_task"] else None
        )
        data["completed_tasks"] = json.loads(data.pop("completed_tasks_json"))
        data["status"] = AssessmentStatus(data["status"])
        raw_protocol = data.pop("protocol_snapshot_json")
        data["protocol_snapshot"] = json.loads(raw_protocol) if raw_protocol else None
        data.setdefault("evaluation_id", None)
        data.setdefault("condition_position", None)
        return TaskAssessment(**data)

    def recover_task_assessment(self, assessment_id: int) -> TaskAssessment:
        """Mark an orphaned in-progress task session aborted; keep the run at the same task."""
        assessment = self.get_task_assessment(assessment_id)
        if assessment is None:
            raise RepositoryError(f"Unknown task assessment {assessment_id}")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            recovered = conn.execute(
                """UPDATE sessions SET status = 'aborted', ended_at = ?
                   WHERE assessment_id = ? AND status = 'in_progress'""",
                (now, assessment_id),
            ).rowcount
            conn.execute(
                "UPDATE task_assessments SET updated_at = ? WHERE assessment_id = ?",
                (now, assessment_id),
            )
        if recovered:
            log.warning(
                "task_assessment_recovered assessment_id=%s aborted_sessions=%s",
                assessment_id, recovered,
            )
        return self.get_task_assessment(assessment_id)

    def complete_task_assessment_session(self, assessment_id: int, session_id: int) -> TaskAssessment:
        """Advance persisted progress after the expected task session completed."""
        assessment = self.get_task_assessment(assessment_id)
        session = self.get_session(session_id)
        if assessment is None or session is None:
            raise RepositoryError("Unknown assessment or session")
        if session.status != SessionStatus.COMPLETED:
            return assessment
        if session.assessment_id != assessment_id:
            raise RepositoryError("Session is not linked to this task assessment")
        if (AssessmentStage(session.assessment_stage), session.task_position,
                ExperimentType(session.experiment_type)) != (
                assessment.stage, assessment.current_position, assessment.current_task,
        ):
            raise RepositoryError("Completed session does not match the current assessment task")

        completed = {key: list(values) for key, values in assessment.completed_tasks.items()}
        key = str(assessment.stage)
        task_value = str(assessment.current_task)
        if task_value not in completed.setdefault(key, []):
            completed[key].append(task_value)

        stage = assessment.stage
        position = assessment.current_position
        order = assessment.order_for_stage()
        next_positions = list(range(position + 1, 4))
        if stage in NON_ANALYSED_STAGES:
            snapshot = assessment.protocol_snapshot or {}
            if stage == AssessmentStage.PRACTICE:
                counts = snapshot.get("practice", {}).get("trial_count", {})
            else:
                counts = snapshot.get("condition_design", {}).get("familiarization", {}).get("trial_count", {})
            next_positions = [
                candidate for candidate in next_positions
                if int(counts.get(str(order[candidate - 1]), 0)) > 0
            ]
        if next_positions:
            position = next_positions[0]
            current_task = ExperimentType(order[position - 1])
            status = AssessmentStatus.IN_PROGRESS
        elif stage in NON_ANALYSED_STAGES:
            stage = AssessmentStage.EXPERIMENTAL
            position = 1
            current_task = ExperimentType(assessment.task_order[0])
            status = AssessmentStatus.IN_PROGRESS
        else:
            current_task = None
            status = AssessmentStatus.COMPLETED

        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE task_assessments
                   SET updated_at = ?, stage = ?, current_position = ?, current_task = ?,
                       completed_tasks_json = ?, status = ?
                   WHERE assessment_id = ?""",
                (
                    now, str(stage), position,
                    None if current_task is None else str(current_task),
                    json.dumps(completed, sort_keys=True), str(status), assessment_id,
                ),
            )
        log.info(
            "task_assessment_advanced assessment_id=%s stage=%s position=%s status=%s",
            assessment_id, stage, position, status,
        )
        return self.get_task_assessment(assessment_id)

    def list_task_assessment_sessions(self, assessment_id: int) -> list[Session]:
        rows = self._conn.execute(
            """SELECT session_id FROM sessions WHERE assessment_id = ?
               ORDER BY session_id""",
            (assessment_id,),
        ).fetchall()
        return [self.get_session(row["session_id"]) for row in rows]

    # ----------------------------------------------------------------- sessions
    def next_session_number(self, player_id: str) -> int:
        """1-based count of sessions this player has started (any type/condition)."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(session_number), 0) AS n FROM sessions WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return int(row["n"]) + 1

    def create_session(self, session: Session) -> Session:
        session.validate()
        if self.get_player(session.player_id) is None:
            raise RepositoryError(f"Unknown player_id {session.player_id!r}")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO sessions (player_id, started_at, experiment_type, condition,
                       session_number, status, crosshair_id, environment_id, random_seed,
                       task_config_json, parent_session_id, recommendation_id, app_version,
                       notes, protocol_version, protocol_snapshot_json, crosshair_snapshot_json,
                       assessment_id, assessment_stage, task_order_mode, task_order_group,
                       task_order_json, task_position, evaluation_id, condition_order_group,
                       condition_order_json, condition_position, initial_baseline_session_id,
                       selected_candidate_id, seed_group)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session.player_id, now, ExperimentType(session.experiment_type).value,
                    Condition(session.condition).value, session.session_number,
                    SessionStatus.IN_PROGRESS.value, session.crosshair_id,
                    session.environment_id, session.random_seed,
                    json.dumps(session.task_config, sort_keys=True) if session.task_config else None,
                    session.parent_session_id, session.recommendation_id, session.app_version,
                    session.notes, session.protocol_version,
                    json.dumps(session.protocol_snapshot, sort_keys=True) if session.protocol_snapshot else None,
                    json.dumps(session.crosshair_snapshot, sort_keys=True) if session.crosshair_snapshot else None,
                    session.assessment_id,
                    None if session.assessment_stage is None else str(session.assessment_stage),
                    None if session.task_order_mode is None else str(session.task_order_mode),
                    session.task_order_group,
                    json.dumps(session.task_order) if session.task_order else None,
                    session.task_position,
                    session.evaluation_id, session.condition_order_group,
                    json.dumps(session.condition_order) if session.condition_order else None,
                    session.condition_position, session.initial_baseline_session_id,
                    session.selected_candidate_id, session.seed_group,
                ),
            )
        session.session_id = cursor.lastrowid
        session.started_at = now
        session.status = SessionStatus.IN_PROGRESS
        log.info(
            "session_created session_id=%s player_id=%s type=%s condition=%s",
            session.session_id, session.player_id, session.experiment_type, session.condition,
        )
        return session

    def finish_session(self, session_id: int, status: SessionStatus) -> None:
        """Mark a session completed or aborted. Aborted sessions keep all raw trials."""
        if status == SessionStatus.IN_PROGRESS:
            raise RepositoryError("finish_session requires a terminal status")
        with self.db.transaction() as conn:
            updated = conn.execute(
                "UPDATE sessions SET status = ?, ended_at = ? "
                "WHERE session_id = ? AND status = 'in_progress'",
                (SessionStatus(status).value, utc_now_iso(), session_id),
            ).rowcount
        if updated != 1:
            raise RepositoryError(f"Session {session_id} is not in progress")
        log.info("session_finished session_id=%s status=%s", session_id, status)

    def get_session(self, session_id: int) -> Session | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        parsed = {
            name: json.loads(raw) if raw else None
            for name, raw in (("task_config", data.pop("task_config_json")),
                              ("protocol_snapshot", data.pop("protocol_snapshot_json", None)),
                              ("crosshair_snapshot", data.pop("crosshair_snapshot_json", None)))
        }
        raw_order = data.pop("task_order_json", None)
        parsed["task_order"] = tuple(json.loads(raw_order)) if raw_order else None
        raw_conditions = data.pop("condition_order_json", None)
        parsed["condition_order"] = tuple(json.loads(raw_conditions)) if raw_conditions else None
        data["condition"] = Condition(data["condition"])
        if data.get("assessment_stage") is not None:
            data["assessment_stage"] = AssessmentStage(data["assessment_stage"])
        if data.get("task_order_mode") is not None:
            data["task_order_mode"] = TaskOrderMode(data["task_order_mode"])
        return Session(**data, **parsed)

    def list_session_summaries(self, player_id: str | None = None) -> list[SessionSummary]:
        sql = """SELECT s.session_id, s.player_id, s.started_at, s.experiment_type,
                        s.condition, s.session_number, s.status, c.name AS crosshair_name,
                        (SELECT COUNT(*) FROM trials t WHERE t.session_id = s.session_id
                             AND (t.trial_phase IS NULL OR t.trial_phase = 'experimental'))
                            AS trial_count,
                        s.task_order_group, s.task_order_json, s.task_position,
                        s.assessment_stage, s.condition_order_group, s.condition_position,
                        s.evaluation_id
                 FROM sessions s JOIN crosshairs c ON c.crosshair_id = s.crosshair_id"""
        params: tuple[str, ...] = ()
        if player_id is not None:
            sql += " WHERE s.player_id = ?"
            params = (player_id,)
        sql += " ORDER BY s.started_at DESC"
        summaries = []
        for row in self._conn.execute(sql, params).fetchall():
            data = dict(row)
            raw_order = data.pop("task_order_json")
            summaries.append(SessionSummary(
                **data, task_order=tuple(json.loads(raw_order)) if raw_order else None
            ))
        return summaries

    # ------------------------------------------------------------------- trials
    def add_trial(
        self,
        trial: Trial,
        samples: Iterable[TrialSample] = (),
        events: Iterable[TrialEvent] = (),
    ) -> Trial:
        """Append one trial with its raw samples/events atomically."""
        trial.validate()
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO trials (session_id, trial_number, recorded_at, task_type,
                       target_id, previous_target_id, target_x, target_y, target_size,
                       target_distance, target_speed, initial_crosshair_x,
                       initial_crosshair_y, result, reaction_time_ms, movement_time_ms,
                       completion_time_ms, error_distance, movement_distance, extra_json,
                       trial_status, timing_quality, trial_phase)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trial.session_id, trial.trial_number, now,
                    ExperimentType(trial.task_type).value, trial.target_id,
                    trial.previous_target_id, trial.target_x, trial.target_y,
                    trial.target_size, trial.target_distance, trial.target_speed,
                    trial.initial_crosshair_x, trial.initial_crosshair_y,
                    TrialResult(trial.result).value, trial.reaction_time_ms,
                    trial.movement_time_ms, trial.completion_time_ms, trial.error_distance,
                    trial.movement_distance, trial.extra_json(),
                    None if trial.trial_status is None else str(trial.trial_status),
                    None if trial.timing_quality is None else str(trial.timing_quality),
                    None if trial.trial_phase is None else str(trial.trial_phase),
                ),
            )
            trial_id = cursor.lastrowid
            conn.executemany(
                """INSERT INTO trial_samples (trial_id, t_ms, cursor_x, cursor_y,
                       target_x, target_y, on_target) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        trial_id, s.t_ms, s.cursor_x, s.cursor_y, s.target_x, s.target_y,
                        None if s.on_target is None else int(s.on_target),
                    )
                    for s in samples
                ],
            )
            conn.executemany(
                """INSERT INTO trial_events (trial_id, t_ms, event_type, x, y, is_hit)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (trial_id, e.t_ms, e.event_type, e.x, e.y,
                     None if e.is_hit is None else int(e.is_hit))
                    for e in events
                ],
            )
        trial.trial_id = trial_id
        trial.recorded_at = now
        return trial

    def list_trials(self, session_id: int) -> list[Trial]:
        rows = self._conn.execute(
            "SELECT * FROM trials WHERE session_id = ? ORDER BY trial_number", (session_id,)
        ).fetchall()
        trials = []
        for row in rows:
            data = dict(row)
            extra = data.pop("extra_json")
            data["task_type"] = ExperimentType(data["task_type"])
            data["result"] = TrialResult(data["result"])
            for key, enum in (("trial_status", TrialStatus), ("timing_quality", TimingQuality),
                              ("trial_phase", TrialPhase)):
                if data.get(key) is not None:
                    data[key] = enum(data[key])
            trials.append(Trial(**data, extra=json.loads(extra) if extra else None))
        return trials

    def list_samples(self, trial_id: int) -> list[TrialSample]:
        rows = self._conn.execute(
            "SELECT t_ms, cursor_x, cursor_y, target_x, target_y, on_target "
            "FROM trial_samples WHERE trial_id = ? ORDER BY t_ms, sample_id",
            (trial_id,),
        ).fetchall()
        return [
            TrialSample(
                t_ms=r["t_ms"], cursor_x=r["cursor_x"], cursor_y=r["cursor_y"],
                target_x=r["target_x"], target_y=r["target_y"],
                on_target=None if r["on_target"] is None else bool(r["on_target"]),
            )
            for r in rows
        ]

    def list_events(self, trial_id: int) -> list[TrialEvent]:
        rows = self._conn.execute(
            "SELECT t_ms, event_type, x, y, is_hit FROM trial_events "
            "WHERE trial_id = ? ORDER BY t_ms, event_id",
            (trial_id,),
        ).fetchall()
        return [
            TrialEvent(
                t_ms=r["t_ms"], event_type=r["event_type"], x=r["x"], y=r["y"],
                is_hit=None if r["is_hit"] is None else bool(r["is_hit"]),
            )
            for r in rows
        ]

    def list_sessions(
        self,
        player_id: str | None = None,
        experiment_type: ExperimentType | None = None,
        condition: Condition | None = None,
        status: SessionStatus | None = None,
        assessment_id: int | None = None,
        assessment_stage: AssessmentStage | None = None,
        evaluation_id: int | None = None,
    ) -> list[Session]:
        """Sessions matching all given filters, newest first."""
        clauses, params = [], []
        for column, value in (("player_id", player_id), ("experiment_type", experiment_type),
                              ("condition", condition), ("status", status),
                              ("assessment_id", assessment_id),
                              ("assessment_stage", assessment_stage),
                              ("evaluation_id", evaluation_id)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(str(value))
        sql = "SELECT session_id FROM sessions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC, session_id DESC"
        return [self.get_session(r["session_id"]) for r in self._conn.execute(sql, params).fetchall()]

    # ------------------------------------------------------- condition evaluations
    def create_condition_evaluation(self, evaluation: ConditionEvaluation) -> ConditionEvaluation:
        """Store a new evaluation cycle; validation of its inputs lives in app.experiment.evaluation."""
        evaluation.validate()
        if self.get_active_condition_evaluation(evaluation.player_id) is not None:
            raise RepositoryError("This participant already has an unfinished crosshair evaluation.")
        now = utc_now_iso()
        with self.db.transaction() as conn:
            if conn.execute("SELECT 1 FROM condition_evaluations WHERE recommendation_id = ?",
                            (evaluation.recommendation_id,)).fetchone():
                raise RepositoryError("A candidate has already been selected for this recommendation run.")
            cursor = conn.execute(
                """INSERT INTO condition_evaluations (
                       player_id, created_at, updated_at, recommendation_id, selected_candidate_id,
                       standard_crosshair_id, standard_crosshair_snapshot_json,
                       initial_baseline_sessions_json, condition_order_group, condition_order_json,
                       condition_assignment_method, current_position, status, protocol_version,
                       protocol_snapshot_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evaluation.player_id, now, now, evaluation.recommendation_id,
                    evaluation.selected_candidate_id, evaluation.standard_crosshair_id,
                    json.dumps(evaluation.standard_crosshair_snapshot, sort_keys=True),
                    json.dumps(evaluation.initial_baseline_sessions, sort_keys=True),
                    evaluation.condition_order_group, json.dumps(list(evaluation.condition_order)),
                    evaluation.condition_assignment_method, evaluation.current_position,
                    str(evaluation.status), evaluation.protocol_version,
                    json.dumps(evaluation.protocol_snapshot, sort_keys=True)
                    if evaluation.protocol_snapshot else None,
                ),
            )
            conn.execute(
                "UPDATE recommendation_candidates SET selected_by_player = "
                "CASE WHEN crosshair_id = ? THEN 1 ELSE 0 END WHERE recommendation_id = ?",
                (evaluation.selected_candidate_id, evaluation.recommendation_id),
            )
        evaluation.evaluation_id = cursor.lastrowid
        evaluation.created_at = evaluation.updated_at = now
        log.info("condition_evaluation_started evaluation_id=%s player_id=%s group=%s candidate=%s",
                 evaluation.evaluation_id, evaluation.player_id, evaluation.condition_order_group,
                 evaluation.selected_candidate_id)
        return evaluation

    @staticmethod
    def _row_to_evaluation(row: sqlite3.Row) -> ConditionEvaluation:
        data = dict(row)
        data["standard_crosshair_snapshot"] = json.loads(data.pop("standard_crosshair_snapshot_json"))
        data["initial_baseline_sessions"] = json.loads(data.pop("initial_baseline_sessions_json"))
        data["condition_order"] = tuple(json.loads(data.pop("condition_order_json")))
        data["status"] = EvaluationStatus(data["status"])
        raw_protocol = data.pop("protocol_snapshot_json")
        data["protocol_snapshot"] = json.loads(raw_protocol) if raw_protocol else None
        return ConditionEvaluation(**data)

    def get_condition_evaluation(self, evaluation_id: int) -> ConditionEvaluation | None:
        row = self._conn.execute(
            "SELECT * FROM condition_evaluations WHERE evaluation_id = ?", (evaluation_id,)
        ).fetchone()
        return self._row_to_evaluation(row) if row else None

    def get_active_condition_evaluation(self, player_id: str) -> ConditionEvaluation | None:
        row = self._conn.execute(
            """SELECT * FROM condition_evaluations WHERE player_id = ? AND status = 'in_progress'
               ORDER BY evaluation_id DESC LIMIT 1""",
            (player_id,),
        ).fetchone()
        return self._row_to_evaluation(row) if row else None

    def list_condition_evaluations(self, player_id: str | None = None) -> list[ConditionEvaluation]:
        sql = "SELECT * FROM condition_evaluations"
        params: tuple = ()
        if player_id is not None:
            sql += " WHERE player_id = ?"
            params = (player_id,)
        sql += " ORDER BY evaluation_id DESC"
        return [self._row_to_evaluation(row) for row in self._conn.execute(sql, params).fetchall()]

    def get_evaluation_task_assessment(self, evaluation_id: int, condition_position: int) -> TaskAssessment | None:
        row = self._conn.execute(
            "SELECT * FROM task_assessments WHERE evaluation_id = ? AND condition_position = ?",
            (evaluation_id, condition_position),
        ).fetchone()
        return self._row_to_task_assessment(row) if row else None

    def advance_condition_evaluation(self, evaluation_id: int) -> ConditionEvaluation:
        """Move to the second condition (or complete) once the current condition assessment is complete."""
        evaluation = self.get_condition_evaluation(evaluation_id)
        if evaluation is None:
            raise RepositoryError(f"Unknown evaluation {evaluation_id}")
        if evaluation.status == EvaluationStatus.COMPLETED:
            return evaluation
        assessment = self.get_evaluation_task_assessment(evaluation_id, evaluation.current_position)
        if assessment is None or assessment.status != AssessmentStatus.COMPLETED:
            return evaluation
        if evaluation.current_position == 1:
            position, status = 2, EvaluationStatus.IN_PROGRESS
        else:
            position, status = 2, EvaluationStatus.COMPLETED
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE condition_evaluations SET updated_at = ?, current_position = ?, status = ?
                   WHERE evaluation_id = ?""",
                (utc_now_iso(), position, str(status), evaluation_id),
            )
        log.info("condition_evaluation_advanced evaluation_id=%s position=%s status=%s",
                 evaluation_id, position, status)
        return self.get_condition_evaluation(evaluation_id)

    # ------------------------------------------------------------ derived metrics
    def save_metrics(
        self, session_id: int, metrics: dict[str, tuple[float | None, str]], analysis_version: str,
    ) -> None:
        """Replace this analysis version's metrics for a session (derived data, recomputable)."""
        now = utc_now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM aim_results WHERE session_id = ? AND analysis_version = ?",
                (session_id, analysis_version),
            )
            conn.executemany(
                """INSERT INTO aim_results (session_id, metric_name, metric_value, unit,
                       analysis_version, computed_at) VALUES (?, ?, ?, ?, ?, ?)""",
                [(session_id, name, value, unit, analysis_version, now)
                 for name, (value, unit) in metrics.items()],
            )

    def get_metrics(self, session_id: int, analysis_version: str) -> dict[str, float | None]:
        rows = self._conn.execute(
            "SELECT metric_name, metric_value FROM aim_results "
            "WHERE session_id = ? AND analysis_version = ?",
            (session_id, analysis_version),
        ).fetchall()
        return {r["metric_name"]: r["metric_value"] for r in rows}

    # ---------------------------------------------------------- recommendations
    def add_recommendation(
        self,
        player_id: str,
        method: str,
        method_version: str,
        weights: dict,
        profile: dict,
        source_session_ids: list[int],
        candidates: list[dict],
    ) -> int:
        """Store a recommendation run and its ranked candidates atomically.

        Each candidate dict needs crosshair_id, rank, score, component_scores, explanation.
        """
        now = utc_now_iso()
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO recommendations (player_id, created_at, method, method_version,
                       weights_json, profile_json, source_session_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (player_id, now, method, method_version, json.dumps(weights, sort_keys=True),
                 json.dumps(profile, sort_keys=True), json.dumps(source_session_ids)),
            )
            recommendation_id = cursor.lastrowid
            conn.executemany(
                """INSERT INTO recommendation_candidates (recommendation_id, crosshair_id, rank,
                       score, component_scores_json, explanation) VALUES (?, ?, ?, ?, ?, ?)""",
                [(recommendation_id, c["crosshair_id"], c["rank"], c["score"],
                  json.dumps(c["component_scores"], sort_keys=True), c["explanation"])
                 for c in candidates],
            )
        log.info("recommendation_created id=%s player_id=%s candidates=%s",
                 recommendation_id, player_id, len(candidates))
        return recommendation_id

    def list_recommendations(self, player_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM recommendations"
        params: tuple = ()
        if player_id is not None:
            sql += " WHERE player_id = ?"
            params = (player_id,)
        sql += " ORDER BY created_at DESC, recommendation_id DESC"
        result = []
        for row in self._conn.execute(sql, params).fetchall():
            data = dict(row)
            data["weights"] = json.loads(data.pop("weights_json"))
            data["profile"] = json.loads(data.pop("profile_json"))
            data["source_session_ids"] = json.loads(data["source_session_ids"])
            data["candidates"] = self.list_recommendation_candidates(data["recommendation_id"])
            result.append(data)
        return result

    def get_recommendation(self, recommendation_id: int) -> dict | None:
        return next(
            (r for r in self.list_recommendations()
             if r["recommendation_id"] == recommendation_id),
            None,
        )

    def list_recommendation_candidates(self, recommendation_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM recommendation_candidates WHERE recommendation_id = ? ORDER BY rank",
            (recommendation_id,),
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["component_scores"] = json.loads(data.pop("component_scores_json"))
            data["selected_by_player"] = bool(data["selected_by_player"])
            result.append(data)
        return result

    def mark_candidate_selected(self, recommendation_id: int, crosshair_id: int) -> None:
        """Record that the player chose this candidate to try.

        Changeable only until an evaluation fixes the candidate for this run.
        """
        fixed = self._conn.execute(
            "SELECT selected_candidate_id FROM condition_evaluations WHERE recommendation_id = ?",
            (recommendation_id,),
        ).fetchone()
        if fixed is not None and fixed["selected_candidate_id"] != crosshair_id:
            raise RepositoryError(
                "The candidate for this recommendation run is fixed by its crosshair evaluation."
            )
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE recommendation_candidates SET selected_by_player = "
                "CASE WHEN crosshair_id = ? THEN 1 ELSE 0 END WHERE recommendation_id = ?",
                (crosshair_id, recommendation_id),
            )

    # -------------------------------------------------------------------- stats
    def counts(self) -> dict[str, int]:
        """Row counts for the main tables (used by the home/settings screens)."""
        tables = ("players", "sessions", "trials", "crosshairs", "recommendations")
        return {
            t: int(self._conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"])
            for t in tables
        }
