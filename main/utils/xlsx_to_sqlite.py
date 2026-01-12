import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


def parse_korean_date_range(date_str: str):
    if date_str is None:
        return None, None
    s = str(date_str).strip()
    if not s or s.lower() == "nan":
        return None, None

    date_patterns = [
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{4}\.\d{1,2}\.\d{1,2}",
        r"\d{4}/\d{1,2}/\d{1,2}",
        r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일",
        r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}",
    ]

    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, s))

    if not dates:
        return None, None

    parsed = []
    fmts = ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일", "%Y.%m.%d"]
    for d in dates:
        d2 = d.replace(" ", "")
        for fmt in fmts:
            try:
                parsed.append(datetime.strptime(d2, fmt))
                break
            except ValueError:
                continue

    if not parsed:
        return None, None

    return min(parsed).strftime("%Y-%m-%d"), max(parsed).strftime("%Y-%m-%d")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.astype(str).str.strip()
    df = df.loc[:, ~df.columns.str.contains(r"^Unnamed", case=False, na=False)]
    df.columns = [
        c.strip()
        .replace(" ", "")
        .replace("/", "")
        .replace("\n", "")
        .replace("\r", "")
        for c in df.columns
    ]
    return df


def convert_xlsx_to_sqlite(xlsx_path: str, db_path: str, table_name: str = "sw_data"):
    xlsx_path = str(Path(xlsx_path))
    db_path = str(Path(db_path))

    # ✅ 무조건 첫 시트(0) 사용
    df = pd.read_excel(
        xlsx_path,
        sheet_name=0,
        engine="openpyxl",
        dtype=object,          # 줄바꿈 포함 원본 최대 유지
        keep_default_na=False, # 빈칸을 NaN으로 바꾸지 않음
    )

    df = _normalize_columns(df)

    # 날짜 컬럼 후보 탐색
    date_col = None
    for c in ["시작날짜종료날짜", "시작날짜종료", "시작일자종료일자"]:
        if c in df.columns:
            date_col = c
            break
    if date_col is None:
        for c in df.columns:
            if ("시작" in c) and ("종료" in c):
                date_col = c
                break

    if date_col is not None:
        df[["시작일자", "종료일자"]] = df[date_col].apply(
            lambda x: pd.Series(parse_korean_date_range(x))
        )
    else:
        df["시작일자"] = ""
        df["종료일자"] = ""

    conn = sqlite3.connect(db_path)

    tmp = f"{table_name}__tmp"
    conn.execute(f'DROP TABLE IF EXISTS "{tmp}"')
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')

    df.to_sql(tmp, conn, index=False, if_exists="replace")

    cols = list(df.columns)
    if "일련번호" not in cols:
        conn.execute(f'ALTER TABLE "{tmp}" RENAME TO "{table_name}"')
        conn.commit()
        conn.close()
        print(f"✅ XLSX({xlsx_path}) → SQLite({db_path}) 저장 완료 (일련번호 없음)")
        return

    columns_definition = ", ".join([f'"{c}" TEXT' for c in cols if c != "일련번호"])
    conn.execute(f'''
        CREATE TABLE "{table_name}" (
            "일련번호" INTEGER PRIMARY KEY,
            {columns_definition}
        );
    ''')

    quoted_columns = ", ".join([f'"{c}"' for c in cols])
    conn.execute(f'''
        INSERT INTO "{table_name}"({quoted_columns})
        SELECT {quoted_columns} FROM "{tmp}";
    ''')

    conn.execute(f'DROP TABLE "{tmp}"')
    conn.commit()
    conn.close()

    print(f"✅ XLSX({xlsx_path}) → SQLite({db_path}) 변환 및 저장 완료")
