import re
import pandas as pd
from datetime import datetime
import sqlite3

# 개선된 날짜 변환 함수
def parse_korean_date_range(date_str):
    if pd.isna(date_str):
        return None, None

    # # 두 자리 연도 보정 (25.02.03 형태 처리)
    def fix_two_digit_year(date):
        return re.sub(r'^(\d{2})\.', r'20\1.', date)

    # 날짜 패턴 추출 (모든 가능성 포함)
    date_patterns = [
        r'\d{4}[\.-]\s?\d{1,2}[\.-]\s?\d{1,2}[일\.]?',
        r'\d{2}[\.-]\d{1,2}[\.-]\d{1,2}[일\.]?',
        r'\d{4}년\s?\d{1,2}월\s?\d{1,2}일',
    ]

    # 전체에서 날짜만 추출
    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, date_str.replace('~', ' ').replace('\n', ' ')))

    cleaned_dates = []
    for date in dates:
        date = fix_two_digit_year(date)  # 두 자리 연도 보정
        date = re.sub(r'[년월일]', '.', date)
        date = re.sub(r'\s+', '', date)
        date = date.strip('.').strip()
        cleaned_dates.append(date)

    parsed_dates = []
    for date in cleaned_dates:
        parsed = False
        for fmt in ["%Y.%m.%d"]:
            try:
                parsed_date = datetime.strptime(date, fmt)
                parsed_dates.append(parsed_date)
                parsed = True
                break
            except:
                continue
        if not parsed:
            print(f"[날짜 변환 실패] 날짜: '{date}'")

    if not parsed_dates:
        return None, None

    start_date = min(parsed_dates).strftime('%Y-%m-%d')
    end_date = max(parsed_dates).strftime('%Y-%m-%d')

    return start_date, end_date

def convert_csv_to_sqlite(csv_path, db_path):
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # 불필요한 Unnamed 컬럼 제거
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

    # 컬럼명 정리: 공백 제거, 특수문자 변경
    df.columns = [
        col.strip().replace(" ", "").replace("/", "").replace("\n", "")
        for col in df.columns
    ]
    print(df.columns.tolist())

    # 날짜 처리 및 새 컬럼 생성
    df[['시작일자', '종료일자']] = df['시작날짜종료날짜'].apply(
        lambda x: pd.Series(parse_korean_date_range(str(x)))
    )

    # SQLite에 연결 및 저장
    conn = sqlite3.connect(db_path)

    conn.execute('DROP TABLE IF EXISTS sw_data')
    conn.execute('DROP TABLE IF EXISTS sw_data_new')

    df.to_sql('sw_data', conn, index=False, if_exists='replace')

    columns_definition = ", ".join([f'"{col}" TEXT' for col in df.columns if col != '일련번호'])
    conn.execute(f'''
        CREATE TABLE sw_data_new (
            일련번호 INTEGER PRIMARY KEY,
            {columns_definition}
        );
    ''')

    quoted_columns = ', '.join([f'"{col}"' for col in df.columns])
    conn.execute(f'''
        INSERT INTO sw_data_new({quoted_columns})
        SELECT {quoted_columns} FROM sw_data;
    ''')

    conn.execute('DROP TABLE sw_data;')
    conn.execute('ALTER TABLE sw_data_new RENAME TO sw_data;')

    conn.commit()
    conn.close()

    print(f"✅ CSV({csv_path}) → SQLite({db_path}) 변환 및 데이터 정제 완료")
