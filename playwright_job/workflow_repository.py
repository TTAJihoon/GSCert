from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


WORKFLOW_DB_RELATIVE_PATH = Path("main") / "data" / "workflow.db"

JOB_STATUS = {"pending", "running", "completed", "failed", "canceled"}
JOB_PROJECT_STATUS = {
    "pending",
    "running",
    "downloaded",
    "inspecting",
    "completed",
    "failed",
    "skipped",
}


class WorkflowDbError(RuntimeError):
    """workflow.db 처리 중 발생하는 기본 예외."""


class WorkflowJobNotFound(WorkflowDbError):
    """작업 ID가 존재하지 않을 때 발생한다."""


class WorkflowJobProjectNotFound(WorkflowDbError):
    """작업에 포함된 프로젝트가 존재하지 않을 때 발생한다."""


def default_workflow_db_path() -> Path:
    return Path(__file__).resolve().parents[1] / WORKFLOW_DB_RELATIVE_PATH


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, str] | None:
    if row is None:
        return None
    return {key: "" if row[key] is None else str(row[key]) for key in row.keys()}


class WorkflowRepository:
    """작업 진행상태와 전역 작업 락을 workflow.db에 저장한다."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_workflow_db_path()

    def initialize_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_job (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT '',
                    progress_message TEXT NOT NULL DEFAULT '',
                    requested_project_count TEXT NOT NULL DEFAULT '0',
                    completed_project_count TEXT NOT NULL DEFAULT '0',
                    failed_project_count TEXT NOT NULL DEFAULT '0',
                    selected_projects_json TEXT NOT NULL DEFAULT '[]',
                    last_error_message TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS automation_job_project (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    project_number TEXT NOT NULL,
                    ecm_row_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    download_dir TEXT NOT NULL DEFAULT '',
                    zip_path TEXT NOT NULL DEFAULT '',
                    current_step TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    retry_count TEXT NOT NULL DEFAULT '0',
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES automation_job(id)
                );

                CREATE INDEX IF NOT EXISTS idx_automation_job_status
                    ON automation_job(status);

                CREATE INDEX IF NOT EXISTS idx_automation_job_project_job_id
                    ON automation_job_project(job_id);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_job_project_unique
                    ON automation_job_project(job_id, project_number);

                CREATE TABLE IF NOT EXISTS automation_lock (
                    id TEXT PRIMARY KEY,
                    locked TEXT NOT NULL,
                    job_id TEXT NOT NULL DEFAULT '',
                    locked_at TEXT NOT NULL DEFAULT '',
                    heartbeat_at TEXT NOT NULL DEFAULT ''
                );
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO automation_lock (id, locked, job_id, locked_at, heartbeat_at)
                VALUES ('global', 'N', '', '', '')
                """
            )
            conn.commit()

    def create_job(
        self,
        project_numbers: Iterable[str],
        *,
        ecm_rows_by_project: Mapping[str, Mapping[str, Any]] | None = None,
        job_id: str | None = None,
    ) -> str:
        numbers = [number.strip() for number in project_numbers if number.strip()]
        if not numbers:
            raise ValueError("작업에 포함할 프로젝트번호가 필요합니다.")

        self.initialize_schema()
        created_job_id = job_id or str(uuid.uuid4())
        now = utc_now_text()
        ecm_rows_by_project = ecm_rows_by_project or {}

        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO automation_job (
                    id,
                    status,
                    requested_at,
                    requested_project_count,
                    selected_projects_json
                )
                VALUES (?, 'pending', ?, ?, ?)
                """,
                (created_job_id, now, str(len(numbers)), json.dumps(numbers, ensure_ascii=False)),
            )

            for project_number in numbers:
                project_id = str(uuid.uuid4())
                ecm_row = ecm_rows_by_project.get(project_number, {})
                conn.execute(
                    """
                    INSERT INTO automation_job_project (
                        id,
                        job_id,
                        project_number,
                        ecm_row_json,
                        status
                    )
                    VALUES (?, ?, ?, ?, 'pending')
                    """,
                    (
                        project_id,
                        created_job_id,
                        project_number,
                        json.dumps(ecm_row, ensure_ascii=False),
                    ),
                )
            conn.commit()

        return created_job_id

    def get_job(self, job_id: str) -> dict[str, str] | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM automation_job WHERE id = ?", (job_id,)).fetchone()
        return _row_to_dict(row)

    def list_jobs(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, str]]:
        self._validate_page(limit, offset)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM automation_job
                ORDER BY requested_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [_row_to_dict(row) for row in rows if row is not None]

    def list_job_projects(self, job_id: str) -> list[dict[str, str]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM automation_job_project
                WHERE job_id = ?
                ORDER BY rowid ASC
                """,
                (job_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows if row is not None]

    def update_job_status(
        self,
        job_id: str,
        status: str,
        *,
        progress_message: str = "",
        last_error_message: str = "",
    ) -> None:
        if status not in JOB_STATUS:
            raise ValueError(f"지원하지 않는 작업 상태입니다: {status}")

        now = utc_now_text()
        started_at = now if status == "running" else None
        completed_at = now if status in {"completed", "failed", "canceled"} else None

        sets = ["status = ?", "progress_message = ?", "last_error_message = ?"]
        params: list[Any] = [status, progress_message, last_error_message]
        if started_at:
            sets.append("started_at = CASE WHEN started_at = '' THEN ? ELSE started_at END")
            params.append(started_at)
        if completed_at:
            sets.append("completed_at = ?")
            params.append(completed_at)
        params.append(job_id)

        with closing(self._connect()) as conn:
            cursor = conn.execute(
                f"UPDATE automation_job SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise WorkflowJobNotFound(f"작업을 찾을 수 없습니다: {job_id}")

    def update_project_status(
        self,
        job_id: str,
        project_number: str,
        status: str,
        *,
        current_step: str = "",
        download_dir: str = "",
        zip_path: str = "",
        error_message: str = "",
    ) -> None:
        if status not in JOB_PROJECT_STATUS:
            raise ValueError(f"지원하지 않는 프로젝트 상태입니다: {status}")

        now = utc_now_text()
        started_at = now if status == "running" else None
        completed_at = now if status in {"completed", "failed", "skipped"} else None

        sets = [
            "status = ?",
            "current_step = ?",
            "download_dir = CASE WHEN ? != '' THEN ? ELSE download_dir END",
            "zip_path = CASE WHEN ? != '' THEN ? ELSE zip_path END",
            "error_message = ?",
        ]
        params: list[Any] = [
            status,
            current_step,
            download_dir,
            download_dir,
            zip_path,
            zip_path,
            error_message,
        ]
        if started_at:
            sets.append("started_at = CASE WHEN started_at = '' THEN ? ELSE started_at END")
            params.append(started_at)
        if completed_at:
            sets.append("completed_at = ?")
            params.append(completed_at)
        params.extend([job_id, project_number])

        with closing(self._connect()) as conn:
            cursor = conn.execute(
                f"""
                UPDATE automation_job_project
                SET {', '.join(sets)}
                WHERE job_id = ? AND project_number = ?
                """,
                params,
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise WorkflowJobProjectNotFound(f"작업 프로젝트를 찾을 수 없습니다: {job_id} / {project_number}")

    def refresh_job_counts(self, job_id: str) -> None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status IN ('completed', 'skipped') THEN 1 ELSE 0 END) AS completed_count,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
                FROM automation_job_project
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            cursor = conn.execute(
                """
                UPDATE automation_job
                SET completed_project_count = ?,
                    failed_project_count = ?
                WHERE id = ?
                """,
                (
                    str(row["completed_count"] or 0),
                    str(row["failed_count"] or 0),
                    job_id,
                ),
            )
            conn.commit()
        if cursor.rowcount == 0:
            raise WorkflowJobNotFound(f"작업을 찾을 수 없습니다: {job_id}")

    def try_acquire_lock(self, job_id: str) -> bool:
        self.initialize_schema()
        now = utc_now_text()

        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT locked FROM automation_lock WHERE id = 'global'").fetchone()
            if row and row["locked"] == "Y":
                conn.rollback()
                return False

            conn.execute(
                """
                UPDATE automation_lock
                SET locked = 'Y',
                    job_id = ?,
                    locked_at = ?,
                    heartbeat_at = ?
                WHERE id = 'global'
                """,
                (job_id, now, now),
            )
            conn.commit()
        return True

    def release_lock(self, job_id: str) -> bool:
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE automation_lock
                SET locked = 'N',
                    job_id = '',
                    locked_at = '',
                    heartbeat_at = ''
                WHERE id = 'global' AND locked = 'Y' AND job_id = ?
                """,
                (job_id,),
            )
            conn.commit()
        return cursor.rowcount > 0

    def heartbeat_lock(self, job_id: str) -> bool:
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE automation_lock
                SET heartbeat_at = ?
                WHERE id = 'global' AND locked = 'Y' AND job_id = ?
                """,
                (utc_now_text(), job_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def get_lock(self) -> dict[str, str]:
        self.initialize_schema()
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM automation_lock WHERE id = 'global'").fetchone()
        lock = _row_to_dict(row)
        if lock is None:
            raise WorkflowDbError("전역 작업 락 row를 찾을 수 없습니다.")
        return lock

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _validate_page(self, limit: int, offset: int) -> None:
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        if limit > 500:
            raise ValueError("limit은 500 이하이어야 합니다.")
        if offset < 0:
            raise ValueError("offset은 0 이상이어야 합니다.")
