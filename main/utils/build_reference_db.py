import csv
import re
import sqlite3
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CSV_PATH = DATA_DIR / "reference.csv"
DB_PATH = DATA_DIR / "reference.db"
TABLE_NAME = "sw_data"
ALIAS_COLUMNS = ("제품설명", "시작일자", "종료일자")
INDEX_COLUMNS = ("일련번호", "인증번호", "시험번호", "회사명", "제품", "시작일자", "종료일자")


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def clean_index_name(value):
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_")
    return f"idx_sw_data_{cleaned or 'column'}"


def format_date(value):
    match = re.search(r"(\d{4})\s*(?:\.|년|-)\s*(\d{1,2})\s*(?:\.|월|-)\s*(\d{1,2})", value or "")
    if not match:
        return ""
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def split_period(value):
    parts = re.split(r"\s*(?:~|～)\s*", value or "", maxsplit=1)
    start = format_date(parts[0]) if parts else ""
    end = format_date(parts[1]) if len(parts) > 1 else ""
    return start, end


def load_rows():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        source_columns = list(reader.fieldnames or [])
        columns = [*source_columns, *(column for column in ALIAS_COLUMNS if column not in source_columns)]
        rows = []
        for row in reader:
            start_date, end_date = split_period(row.get("시작날짜/\n종료날짜", ""))
            row["제품설명"] = row.get("제품 설명", "")
            row["시작일자"] = start_date
            row["종료일자"] = end_date
            rows.append([row.get(column, "") for column in columns])
    return columns, rows


def build_reference_db():
    columns, rows = load_rows()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {quote_identifier(TABLE_NAME)}")
        column_sql = ", ".join(f"{quote_identifier(column)} TEXT" for column in columns)
        conn.execute(f"CREATE TABLE {quote_identifier(TABLE_NAME)} ({column_sql})")

        insert_columns = ", ".join(quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        conn.executemany(
            f"INSERT INTO {quote_identifier(TABLE_NAME)} ({insert_columns}) VALUES ({placeholders})",
            rows,
        )

        for column in INDEX_COLUMNS:
            if column in columns:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {quote_identifier(clean_index_name(column))} "
                    f"ON {quote_identifier(TABLE_NAME)} ({quote_identifier(column)})"
                )

    return len(rows), len(columns)


if __name__ == "__main__":
    row_count, column_count = build_reference_db()
    print(f"{DB_PATH} 생성 완료: {row_count} rows, {column_count} columns")
