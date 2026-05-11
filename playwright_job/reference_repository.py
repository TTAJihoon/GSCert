from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping


REFERENCE_DB_RELATIVE_PATH = Path("main") / "data" / "reference.db"
ECM_TABLE = "ecm"

ECM_COLUMNS = (
    "번호",
    "인증일자",
    "프로젝트번호",
    "회사명",
    "제품명",
    "시험PL",
    "점검결과",
    "계약서",
    "합의서(PDF)",
    "수수료산정표",
    "시험환경구성도",
    "품질특성별제품정보기재사항",
    "기능리스트",
    "시험계획서(PDF)",
    "점검표(PDF)",
    "최초/최종형상RawData",
    "테스트케이스",
    "결함리포트",
    "1차/2차/성능/보안RawData",
    "시험성적서(PDF)",
    "시험기록서",
    "품질평가보고서",
    "품질검사표",
    "SW저작권확인서",
    "홍보이미지",
)

PROJECT_LIST_COLUMNS = (
    "번호",
    "인증일자",
    "프로젝트번호",
    "회사명",
    "제품명",
    "시험PL",
    "점검결과",
)

FILTER_COLUMNS = {
    "project_number": "프로젝트번호",
    "company": "회사명",
    "product": "제품명",
    "test_pl": "시험PL",
    "review_result": "점검결과",
}


class ReferenceDbError(RuntimeError):
    """reference.db 조회 중 발생하는 기본 예외."""


class ReferenceDbNotFound(ReferenceDbError):
    """reference.db 파일이 아직 준비되지 않았을 때 발생한다."""


class ReferenceTableNotFound(ReferenceDbError):
    """ecm 테이블이 없을 때 발생한다."""


class ReferenceColumnMismatch(ReferenceDbError):
    """ecm 테이블의 필수 컬럼이 누락되었을 때 발생한다."""


def default_reference_db_path() -> Path:
    return Path(__file__).resolve().parents[1] / REFERENCE_DB_RELATIVE_PATH


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _row_to_dict(row: sqlite3.Row) -> dict[str, str]:
    return {key: "" if row[key] is None else str(row[key]) for key in row.keys()}


class EcmProjectRepository:
    """main/data/reference.db의 ecm 프로젝트 기준 정보를 조회한다."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_reference_db_path()

    def validate_schema(self) -> None:
        with closing(self._connect()) as conn:
            if not self._table_exists(conn):
                raise ReferenceTableNotFound(f"{ECM_TABLE} 테이블을 찾을 수 없습니다: {self.db_path}")

            actual_columns = self._fetch_table_columns(conn)
            missing_columns = [column for column in ECM_COLUMNS if column not in actual_columns]
            if missing_columns:
                joined = ", ".join(missing_columns)
                raise ReferenceColumnMismatch(f"ecm 테이블 필수 컬럼이 누락되었습니다: {joined}")

    def get_project(self, project_number: str) -> dict[str, str] | None:
        project_number = project_number.strip()
        if not project_number:
            return None

        where_sql, params = self._build_where({"project_number": project_number}, exact_project_number=True)
        sql = self._select_sql(ECM_COLUMNS, where_sql=where_sql, limit=1)
        with closing(self._connect()) as conn:
            row = conn.execute(sql, [*params, 1]).fetchone()
        return _row_to_dict(row) if row else None

    def list_projects(
        self,
        filters: Mapping[str, str] | None = None,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, str]]:
        checked_limit, checked_offset = self._normalize_page(limit, offset)
        where_sql, params = self._build_where(filters or {})
        sql = self._select_sql(
            PROJECT_LIST_COLUMNS,
            where_sql=where_sql,
            order_by=("인증일자", "프로젝트번호"),
            limit=checked_limit,
            offset=checked_offset,
        )
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, [*params, checked_limit, checked_offset]).fetchall()
        return [_row_to_dict(row) for row in rows]

    def count_projects(self, filters: Mapping[str, str] | None = None) -> int:
        where_sql, params = self._build_where(filters or {})
        sql = f"SELECT COUNT(*) AS cnt FROM {_quote_identifier(ECM_TABLE)}"
        if where_sql:
            sql = f"{sql} WHERE {where_sql}"

        with closing(self._connect()) as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["cnt"])

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise ReferenceDbNotFound(f"reference.db 파일을 찾을 수 없습니다: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (ECM_TABLE,),
        ).fetchone()
        return row is not None

    def _fetch_table_columns(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({_quote_identifier(ECM_TABLE)})").fetchall()
        return {str(row["name"]) for row in rows}

    def _select_sql(
        self,
        columns: tuple[str, ...],
        *,
        where_sql: str = "",
        order_by: tuple[str, ...] = (),
        limit: int | None = None,
        offset: int | None = None,
    ) -> str:
        selected = ", ".join(_quote_identifier(column) for column in columns)
        sql = f"SELECT {selected} FROM {_quote_identifier(ECM_TABLE)}"
        if where_sql:
            sql = f"{sql} WHERE {where_sql}"
        if order_by:
            ordered = ", ".join(_quote_identifier(column) for column in order_by)
            sql = f"{sql} ORDER BY {ordered} DESC"
        if limit is not None:
            sql = f"{sql} LIMIT ?"
        if offset is not None:
            sql = f"{sql} OFFSET ?"
        return sql

    def _build_where(
        self,
        filters: Mapping[str, str],
        *,
        exact_project_number: bool = False,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        for filter_name, raw_value in filters.items():
            if filter_name not in FILTER_COLUMNS:
                raise ValueError(f"지원하지 않는 검색 조건입니다: {filter_name}")

            value = raw_value.strip()
            if not value:
                continue

            column = FILTER_COLUMNS[filter_name]
            if exact_project_number and filter_name == "project_number":
                clauses.append(f"{_quote_identifier(column)} = ?")
                params.append(value)
            else:
                clauses.append(f"{_quote_identifier(column)} LIKE ?")
                params.append(f"%{value}%")

        return " AND ".join(clauses), params

    def _normalize_page(self, limit: int, offset: int) -> tuple[int, int]:
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        if limit > 500:
            raise ValueError("limit은 500 이하이어야 합니다.")
        if offset < 0:
            raise ValueError("offset은 0 이상이어야 합니다.")
        return limit, offset
