import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from main.views.review.ecm_download_review_centers import (
    DownloadReviewCenterError,
    center_label,
    normalize_center_code,
    reference_db_path,
)


DEFAULT_ECM_TABLE = "ecm_list"
REQUIRED_COLUMNS = (
    "프로젝트번호",
    "인증일자",
    "회사명",
    "제품명",
    "시험PL",
    "점검결과",
)
OPTIONAL_COLUMNS = (
    "WD",
    "신청일",
    "계약일",
    "점검날짜",
)
ARTIFACT_REVIEW_COLUMNS = (
    "계약서",
    "합의서(PDF)",
    "수수료산정표",
    "시험환경구성도",
    "품질특성별제품정보기재사항",
    "기능리스트",
    "시험계획서(PDF)",
    "최초/최종형상RawData",
    "테스트케이스",
    "결함리포트",
    "점검표(PDF)",
    "1차/2차/성능/보안RawData",
    "시험성적서(PDF)",
    "시험기록서",
    "품질평가보고서",
    "품질검사표",
    "SW저작권확인서",
    "홍보이미지",
)
MUTABLE_REVIEW_COLUMNS = ("점검결과", *ARTIFACT_REVIEW_COLUMNS)
QUERY_PARAM_NAMES = {
    "project_number",
    "company",
    "product",
    "pl",
    "review",
    "cert_date",
    "q",
    "center",
    "limit",
    "offset",
    "sort",
}
SORT_NAMES = {
    "cert_date_desc",
    "cert_date_asc",
    "project_number_desc",
    "project_number_asc",
}
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_QUERY_LENGTH = 100
COMPLETED_REVIEW_VALUES = {"O", "완료"}
NEEDS_FIX_REVIEW_VALUES = {"X", "수정 필요"}
FAILED_REVIEW_VALUES = {"실패"}
HELD_REVIEW_VALUES = {"보류"}
UNREVIEWED_REVIEW_VALUES = {"", "미점검"}


class ReferenceDbError(Exception):
    error_code = "reference_db_error"


class ReferenceDbMissing(ReferenceDbError):
    error_code = "reference_db_missing"


class ReferenceDbSchemaError(ReferenceDbError):
    error_code = "reference_db_schema_error"


class ReferenceQueryError(ValueError):
    error_code = "invalid_query"


@dataclass(frozen=True)
class ProjectQuery:
    center_code: str
    filters: dict
    limit: int
    offset: int
    sort: str


def list_projects(query_params):
    query = parse_project_query(query_params)
    db_path = Path(reference_db_path(query.center_code))

    if not db_path.exists():
        raise ReferenceDbMissing("기준 DB 파일이 없습니다.")

    table_name = _table_name()

    try:
        with closing(_connect_readonly(db_path)) as conn:
            columns = _get_columns(conn, table_name)
            _validate_columns(columns)
            where_sql, params = _build_where(query.filters)
            total = _count_projects(conn, table_name, where_sql, params)
            items = _fetch_projects(conn, table_name, columns, where_sql, params, query)
    except ReferenceDbError:
        raise
    except sqlite3.Error as exc:
        raise ReferenceDbError("기준 DB 조회 중 오류가 발생했습니다.") from exc

    return {
        "success": True,
        "items": items,
        "pagination": {
            "total": total,
            "limit": query.limit,
            "offset": query.offset,
            "has_more": query.offset + len(items) < total,
        },
        "sort": query.sort,
    }


def get_projects_by_numbers(project_numbers, center_code=None):
    center_code = normalize_center_code(center_code)
    db_path = Path(reference_db_path(center_code))

    if not db_path.exists():
        raise ReferenceDbMissing("기준 DB 파일이 없습니다.")

    table_name = _table_name()

    try:
        with closing(_connect_readonly(db_path)) as conn:
            columns = _get_columns(conn, table_name)
            _validate_columns(columns)
            rows_by_number = _fetch_projects_by_numbers(conn, table_name, columns, project_numbers, center_code)
    except ReferenceDbError:
        raise
    except sqlite3.Error as exc:
        raise ReferenceDbError("기준 DB 조회 중 오류가 발생했습니다.") from exc

    return [rows_by_number.get(number) for number in project_numbers]


def write_project_review_result(project_number, review, artifact_results=None, inspected_at=None, center_code=None):
    center_code = normalize_center_code(center_code)
    number = _clean(project_number)
    if not number:
        raise ReferenceQueryError("프로젝트번호가 필요합니다.")

    review_value = _normalize_review_write_value(review)
    if not review_value:
        raise ReferenceQueryError("점검결과 값이 필요합니다.")

    artifact_results = artifact_results or {}
    if not isinstance(artifact_results, dict):
        raise ReferenceQueryError("artifact_results는 객체여야 합니다.")

    unknown_columns = sorted(set(artifact_results) - set(ARTIFACT_REVIEW_COLUMNS))
    if unknown_columns:
        raise ReferenceQueryError(
            "수정할 수 없는 점검 컬럼이 포함되어 있습니다: " + ", ".join(unknown_columns)
        )

    db_path = Path(reference_db_path(center_code))
    if not db_path.exists():
        raise ReferenceDbMissing("기준 DB 파일이 없습니다.")

    table_name = _table_name()
    try:
        with closing(_connect_writable(db_path)) as conn:
            columns = _get_columns(conn, table_name)
            _validate_write_columns(columns, artifact_results)
            updates = _build_review_updates(review_value, artifact_results, columns, inspected_at)
            updated = _update_project_review_row(conn, table_name, number, updates)
    except ReferenceDbError:
        raise
    except sqlite3.Error as exc:
        raise ReferenceDbError("기준 DB 갱신 중 오류가 발생했습니다.") from exc

    return {
        "success": True,
        "project_number": number,
        "updated_columns": updated,
    }


def parse_project_query(query_params):
    unknown = set(query_params.keys()) - QUERY_PARAM_NAMES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ReferenceQueryError(f"지원하지 않는 조회 조건입니다: {names}")

    try:
        center_code = normalize_center_code(query_params.get("center"))
    except DownloadReviewCenterError as exc:
        raise ReferenceQueryError(str(exc)) from exc
    filters = {
        "project_number": _clean(query_params.get("project_number")),
        "company": _clean(query_params.get("company")),
        "product": _clean(query_params.get("product")),
        "pl": _clean(query_params.get("pl")),
        "review": _clean(query_params.get("review")),
        "cert_date": _clean(query_params.get("cert_date")),
        "q": _clean(query_params.get("q")),
    }
    for name, value in filters.items():
        if value and len(value) > MAX_QUERY_LENGTH:
            raise ReferenceQueryError(f"{name} 조회 조건은 {MAX_QUERY_LENGTH}자 이하로 입력해야 합니다.")

    limit = _parse_int(query_params.get("limit"), DEFAULT_LIMIT, "limit")
    offset = _parse_int(query_params.get("offset"), 0, "offset")
    if limit < 1 or limit > MAX_LIMIT:
        raise ReferenceQueryError(f"limit은 1부터 {MAX_LIMIT} 사이여야 합니다.")
    if offset < 0:
        raise ReferenceQueryError("offset은 0 이상이어야 합니다.")

    sort = _clean(query_params.get("sort")) or "cert_date_desc"
    if sort not in SORT_NAMES:
        raise ReferenceQueryError(f"지원하지 않는 정렬 방식입니다: {sort}")

    return ProjectQuery(center_code=center_code, filters=filters, limit=limit, offset=offset, sort=sort)


def _connect_readonly(db_path):
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = TRUE")
    return conn


def _connect_writable(db_path):
    timeout = getattr(settings, "REFERENCE_DB_WRITE_TIMEOUT_SECONDS", 10)
    busy_timeout_ms = getattr(settings, "REFERENCE_DB_BUSY_TIMEOUT_MS", 10000)
    uri = f"{db_path.resolve().as_uri()}?mode=rw"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    return conn


def _table_name():
    return getattr(settings, "REFERENCE_DB_TABLE", DEFAULT_ECM_TABLE)


def _get_columns(conn, table_name):
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone():
        raise ReferenceDbSchemaError(f"기준 DB에 {table_name} 테이블이 없습니다.")

    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    return {row["name"] for row in rows}


def _validate_columns(columns):
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ReferenceDbSchemaError(
            "기준 DB 테이블에 필수 컬럼이 없습니다: " + ", ".join(missing)
        )


def _validate_write_columns(columns, artifact_results):
    missing = [
        column
        for column in ("프로젝트번호", "점검결과", *artifact_results.keys())
        if column not in columns
    ]
    if missing:
        raise ReferenceDbSchemaError(
            "기준 DB 테이블에 갱신할 점검 컬럼이 없습니다: " + ", ".join(missing)
        )


def _build_where(filters):
    clauses = []
    params = []
    like_filters = {
        "project_number": "프로젝트번호",
        "company": "회사명",
        "product": "제품명",
        "pl": "시험PL",
    }

    for filter_name, column_name in like_filters.items():
        value = filters.get(filter_name)
        if value:
            clauses.append(f"{_quote_identifier(column_name)} LIKE ? ESCAPE '\\'")
            params.append(_like_param(value))

    if filters.get("review"):
        review_values = _review_filter_values(filters["review"])
        if review_values:
            placeholders = ", ".join("?" for _ in review_values)
            clauses.append(f"COALESCE({_quote_identifier('점검결과')}, '') IN ({placeholders})")
            params.extend(review_values)
        else:
            clauses.append(f"{_quote_identifier('점검결과')} = ?")
            params.append(filters["review"])

    if filters.get("cert_date"):
        clauses.append(f"{_quote_identifier('인증일자')} = ?")
        params.append(filters["cert_date"])

    if filters.get("q"):
        search_columns = ("프로젝트번호", "회사명", "제품명", "시험PL")
        clauses.append(
            "("
            + " OR ".join(
                f"{_quote_identifier(column)} LIKE ? ESCAPE '\\'"
                for column in search_columns
            )
            + ")"
        )
        params.extend([_like_param(filters["q"])] * len(search_columns))

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _count_projects(conn, table_name, where_sql, params):
    sql = f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}{where_sql}"
    return int(conn.execute(sql, params).fetchone()[0])


def _fetch_projects(conn, table_name, columns, where_sql, params, query):
    select_columns = [*REQUIRED_COLUMNS, *(column for column in OPTIONAL_COLUMNS if column in columns)]
    sql = (
        "SELECT "
        + ", ".join(_quote_identifier(column) for column in select_columns)
        + f" FROM {_quote_identifier(table_name)}"
        + where_sql
        + " ORDER BY "
        + _order_by_sql(query.sort)
        + " LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*params, query.limit, query.offset]).fetchall()
    return [_serialize_project(row, columns, query.center_code) for row in rows]


def _fetch_projects_by_numbers(conn, table_name, columns, project_numbers, center_code):
    if not project_numbers:
        return {}

    select_columns = [*REQUIRED_COLUMNS, *(column for column in OPTIONAL_COLUMNS if column in columns)]
    placeholders = ", ".join("?" for _ in project_numbers)
    sql = (
        "SELECT "
        + ", ".join(_quote_identifier(column) for column in select_columns)
        + f" FROM {_quote_identifier(table_name)}"
        + f" WHERE {_quote_identifier('프로젝트번호')} IN ({placeholders})"
    )
    rows = conn.execute(sql, project_numbers).fetchall()
    return {
        _row_value(row, "프로젝트번호"): _serialize_project(row, columns, center_code)
        for row in rows
    }


def _build_review_updates(review, artifact_results, columns, inspected_at):
    updates = {"점검결과": review}
    for column in ARTIFACT_REVIEW_COLUMNS:
        if column in artifact_results:
            updates[column] = _normalize_artifact_write_value(artifact_results[column], column)
    if inspected_at and "점검날짜" in columns:
        updates["점검날짜"] = _format_inspection_date(inspected_at)
    return updates


def _update_project_review_row(conn, table_name, project_number, updates):
    set_sql = ", ".join(f"{_quote_identifier(column)} = ?" for column in updates)
    sql = (
        f"UPDATE {_quote_identifier(table_name)}"
        f" SET {set_sql}"
        f" WHERE {_quote_identifier('프로젝트번호')} = ?"
    )
    params = [*updates.values(), project_number]
    with conn:
        cursor = conn.execute(sql, params)
        if cursor.rowcount != 1:
            raise ReferenceDbError(
                "ecmlist.db 프로젝트번호가 고유하지 않거나 찾을 수 없습니다."
            )
    return list(updates.keys())


def _serialize_project(row, columns, center_code):
    review_raw = _row_value(row, "점검결과")
    review = review_label(review_raw)
    return {
        "center_code": center_code,
        "center_label": center_label(center_code),
        "project_number": _row_value(row, "프로젝트번호"),
        "cert_date": _row_value(row, "인증일자"),
        "company": _row_value(row, "회사명"),
        "product": _row_value(row, "제품명"),
        "pl": _row_value(row, "시험PL"),
        "wd": _row_value(row, "WD") if "WD" in columns else "",
        "request_date": _row_value(row, "신청일") if "신청일" in columns else "",
        "contract_date": _row_value(row, "계약일") if "계약일" in columns else "",
        "review": review,
        "review_raw": review_raw,
        "inspection_date": _row_value(row, "점검날짜") if "점검날짜" in columns else "",
        "selectable": not is_completed_review_value(review_raw),
    }


def review_label(value):
    cleaned = _clean(value)
    if cleaned in COMPLETED_REVIEW_VALUES:
        return "완료"
    if cleaned in NEEDS_FIX_REVIEW_VALUES:
        return "수정 필요"
    if cleaned in FAILED_REVIEW_VALUES:
        return "실패"
    if cleaned in HELD_REVIEW_VALUES:
        return "보류"
    return "미점검"


def is_completed_review_value(value):
    return _clean(value) in COMPLETED_REVIEW_VALUES


def _review_filter_values(value):
    cleaned = _clean(value)
    if cleaned in COMPLETED_REVIEW_VALUES:
        return sorted(COMPLETED_REVIEW_VALUES)
    if cleaned in NEEDS_FIX_REVIEW_VALUES:
        return sorted(NEEDS_FIX_REVIEW_VALUES)
    if cleaned in FAILED_REVIEW_VALUES:
        return sorted(FAILED_REVIEW_VALUES)
    if cleaned in HELD_REVIEW_VALUES:
        return sorted(HELD_REVIEW_VALUES)
    if cleaned in UNREVIEWED_REVIEW_VALUES:
        return sorted(UNREVIEWED_REVIEW_VALUES)
    return None


def _normalize_review_write_value(value):
    cleaned = _clean(value)
    if cleaned in COMPLETED_REVIEW_VALUES or cleaned in {"정상", "pass", "PASS"}:
        return "O"
    if cleaned in NEEDS_FIX_REVIEW_VALUES or cleaned in {"부적합", "fail", "FAIL"}:
        return "X"
    if cleaned in FAILED_REVIEW_VALUES or cleaned in {"작업실패", "작업 실패", "error", "ERROR"}:
        return "실패"
    raise ReferenceQueryError("점검결과는 O, X 또는 실패만 기록할 수 있습니다.")


def _normalize_artifact_write_value(value, column):
    cleaned = _clean(value)
    if cleaned in {"", "O", "X"}:
        return cleaned
    if cleaned in {"정상", "완료", "pass", "PASS"}:
        return "O"
    if cleaned in {"부적합", "오류", "fail", "FAIL", "error", "ERROR"}:
        return "X"
    raise ReferenceQueryError(f"{column} 점검 컬럼은 O 또는 X만 기록할 수 있습니다.")


def _order_by_sql(sort):
    project_number = _quote_identifier("프로젝트번호")
    if sort == "project_number_desc":
        return f"{project_number} DESC"
    if sort == "project_number_asc":
        return f"{project_number} ASC"

    direction = "ASC" if sort == "cert_date_asc" else "DESC"
    return f"{_cert_date_sort_expr()} {direction}, {project_number} {direction}"


def _cert_date_sort_expr():
    cert_date = _quote_identifier("인증일자")
    slash_pos = f"instr({cert_date}, '/')"
    return (
        "CASE "
        f"WHEN {slash_pos} > 0 THEN "
        f"CAST(substr({cert_date}, 1, {slash_pos} - 1) AS INTEGER) * 100 + "
        f"CAST(substr({cert_date}, {slash_pos} + 1) AS INTEGER) "
        "ELSE 0 END"
    )


def _parse_int(value, default, name):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReferenceQueryError(f"{name}은 숫자여야 합니다.") from exc


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _like_param(value):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _row_value(row, column_name):
    value = row[column_name]
    if value is None:
        return ""
    return str(value).strip()


def _format_inspection_date(value):
    if hasattr(value, "astimezone"):
        value = timezone.localtime(value)
    if hasattr(value, "strftime"):
        return value.strftime("%Y.%m.%d %H:%M")
    return str(value)


def _quote_identifier(identifier):
    return '"' + identifier.replace('"', '""') + '"'
