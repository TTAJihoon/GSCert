import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd


# 전각 숫자(예: '２０２３')를 반각으로 바꾸기 위한 변환표.
_FULLWIDTH_DIGITS = {ord("０") + i: str(i) for i in range(10)}

# '연.월.일'을 한 번에 잡는 통합 정규식.
#  - 구분자: '.', '-', '/', 한글 '년/월/일' 을 각 위치에서 독립적으로 허용해
#    '2008-06.30' 같은 혼용 표기와 구분자 앞뒤 공백('2015.12. 21', '2014. 6. 23')을 모두 흡수한다.
#  - 연도는 4자리('2023')뿐 아니라 2자리('25.02.06')도 인식한다.
_DATE_RE = re.compile(
    r"(\d{4}|\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
)


def normalize_cell_text(value):
    r"""엑셀 셀 텍스트의 줄바꿈 표기를 '\n' 하나로 통일한다.

    xlsx(OOXML)는 셀 안의 캐리지 리턴(CR, U+000D)을 XML로 보존하지 못해
    '_x000D_' 라는 문자열로 escape 해서 저장하고, openpyxl/pandas 는 이를
    되돌리지 않고 그대로 돌려준다(예: '㈜웨어비즈_x000D_ WAREBIZ Co., Ltd.').
    이 '_x000D_' 를 실제 CR 로 되돌린 뒤 CRLF/CR 를 단일 '\n' 으로 정규화한다.
    원래 CRLF('_x000D_\n')였던 자리가 '\n\n' 으로 겹치지 않게 한다.
    """
    if value is None:
        return value
    s = str(value).replace("_x000D_", "\r")
    return s.replace("\r\n", "\n").replace("\r", "\n")


def parse_korean_date_range(date_str: str):
    """'시작날짜/종료날짜'(M열) 셀에서 가장 이른 날짜와 가장 늦은 날짜를 뽑는다.

    원본은 연.월.일 구분자('.', '-', '/', '년월일'), 자리수(2/4자리 연도, 0-패딩 유무),
    공백, 재시험/재계약 여러 구간, 전각 숫자, 엑셀 줄바꿈('_x000D_') 등 표기가
    제각각이라, 개별 포맷 문자열로 strptime 하지 않고 셀 안의 모든 날짜 토큰을
    정규식으로 훑어 (min, max) 를 반환한다. 하나도 못 찾으면 (None, None).
    """
    if date_str is None:
        return None, None
    s = str(date_str)
    if not s.strip() or s.strip().lower() == "nan":
        return None, None

    # 엑셀 셀 내 줄바꿈 escape('_x000D_')와 전각 숫자를 정규화한다.
    s = s.replace("_x000D_", " ").translate(_FULLWIDTH_DIGITS)

    parsed = []
    for year, month, day in _DATE_RE.findall(s):
        y = int(year)
        if len(year) == 2:  # 2자리 연도는 2000년대로 해석한다.
            y += 2000
        try:
            parsed.append(datetime(y, int(month), int(day)))
        except ValueError:
            # '2014.00.00' 처럼 실제로 존재할 수 없는 날짜(월/일 0 등)는 건너뛴다.
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


def _ensure_sw_category_column(df: pd.DataFrame) -> pd.DataFrame:
    if "SW분류" in df.columns:
        return df

    for alias in ["SW구분", "SW분류명", "SW유형", "소프트웨어분류"]:
        if alias in df.columns:
            df["SW분류"] = df[alias]
            return df

    # 원천 xlsx의 G열이 SW분류로 들어오는 변형을 대비한다.
    if len(df.columns) >= 7:
        g_column = df.columns[6]
        non_sw_columns = {"일련번호", "인증번호", "인증일자", "회사명", "제품", "등급", "시험번호"}
        if g_column not in non_sw_columns:
            df["SW분류"] = df[g_column]
            return df

    df["SW분류"] = ""
    return df


def convert_xlsx_to_sqlite(
    xlsx_path: str,
    db_path: str,
    table_name: str = "sw_data",
    *,
    force: bool = False,
):
    xlsx_path = Path(xlsx_path)
    db_path = Path(db_path)

    df = pd.read_excel(
        str(xlsx_path),
        sheet_name=0,
        engine="openpyxl",
        dtype=object,          # 줄바꿈 포함 원본 최대 유지
        keep_default_na=False, # 빈칸을 NaN으로 바꾸지 않음
    )

    df = _normalize_columns(df)
    df = _ensure_sw_category_column(df)

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

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_name(f".{db_path.name}.tmp")
    if temp_path.exists():
        temp_path.unlink()

    try:
        _write_dataframe_to_sqlite(df, temp_path, table_name)
        if not force and db_path.exists() and _same_sqlite_table(db_path, temp_path, table_name):
            temp_path.unlink()
            print(f"[OK] XLSX({xlsx_path}) -> SQLite({db_path}) no changes")
            return False

        temp_path.replace(db_path)
        print(f"[OK] XLSX({xlsx_path}) -> SQLite({db_path}) converted and saved")
        return True
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_dataframe_to_sqlite(df: pd.DataFrame, db_path: Path, table_name: str):
    conn = sqlite3.connect(str(db_path))

    tmp = f"{table_name}__tmp"
    conn.execute(f'DROP TABLE IF EXISTS "{tmp}"')
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')

    df.to_sql(tmp, conn, index=False, if_exists="replace")

    cols = list(df.columns)
    if "일련번호" not in cols:
        conn.execute(f'ALTER TABLE "{tmp}" RENAME TO "{table_name}"')
        conn.commit()
        conn.close()
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


def _same_sqlite_table(left_path: Path, right_path: Path, table_name: str) -> bool:
    try:
        return _table_snapshot(left_path, table_name) == _table_snapshot(right_path, table_name)
    except sqlite3.Error:
        return False


def _table_snapshot(db_path: Path, table_name: str):
    conn = sqlite3.connect(str(db_path))
    try:
        table_info = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        columns = [(row[1], row[2], row[5]) for row in table_info]
        if not columns:
            return (), ()

        column_names = [row[0] for row in columns]
        quoted_columns = ", ".join(f'"{column}"' for column in column_names)
        if "일련번호" in column_names:
            order_sql = ' ORDER BY "일련번호"'
        else:
            order_sql = " ORDER BY rowid"
        rows = conn.execute(f'SELECT {quoted_columns} FROM "{table_name}"{order_sql}').fetchall()
        return tuple(columns), tuple(tuple(row) for row in rows)
    finally:
        conn.close()
