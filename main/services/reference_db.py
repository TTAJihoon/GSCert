import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


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
    "점검날짜",
)
QUERY_PARAM_NAMES = {
    "project_number",
    "company",
    "product",
    "pl",
    "review",
    "cert_date",
    "q",
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
    filters: dict
    limit: int
    offset: int
    sort: str


def list_projects(query_params):
    query = parse_project_query(query_params)
    db_path = Path(getattr(settings, "REFERENCE_DB_PATH"))

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


def get_projects_by_numbers(project_numbers):
    db_path = Path(getattr(settings, "REFERENCE_DB_PATH"))

    if not db_path.exists():
        raise ReferenceDbMissing("기준 DB 파일이 없습니다.")

    table_name = _table_name()

    try:
        with closing(_connect_readonly(db_path)) as conn:
            columns = _get_columns(conn, table_name)
            _validate_columns(columns)
            rows_by_number = _fetch_projects_by_numbers(conn, table_name, columns, project_numbers)
    except ReferenceDbError:
        raise
    except sqlite3.Error as exc:
        raise ReferenceDbError("기준 DB 조회 중 오류가 발생했습니다.") from exc

    return [rows_by_number.get(number) for number in project_numbers]


def parse_project_query(query_params):
    unknown = set(query_params.keys()) - QUERY_PARAM_NAMES
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ReferenceQueryError(f"지원하지 않는 조회 조건입니다: {names}")

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

    return ProjectQuery(filters=filters, limit=limit, offset=offset, sort=sort)


def _connect_readonly(db_path):
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = TRUE")
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
    return [_serialize_project(row, columns) for row in rows]


def _fetch_projects_by_numbers(conn, table_name, columns, project_numbers):
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
        _row_value(row, "프로젝트번호"): _serialize_project(row, columns)
        for row in rows
    }


def _serialize_project(row, columns):
    review = _row_value(row, "점검결과")
    return {
        "project_number": _row_value(row, "프로젝트번호"),
        "cert_date": _row_value(row, "인증일자"),
        "company": _row_value(row, "회사명"),
        "product": _row_value(row, "제품명"),
        "pl": _row_value(row, "시험PL"),
        "review": review,
        "inspection_date": _row_value(row, "점검날짜") if "점검날짜" in columns else "",
        "selectable": review != "완료",
    }


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


def _quote_identifier(identifier):
    return '"' + identifier.replace('"', '""') + '"'
