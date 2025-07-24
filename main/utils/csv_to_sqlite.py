import re
import pandas as pd
from datetime import datetime
import sqlite3

# 개선된 날짜 변환 함수
def parse_korean_date_range(date_str):
    if pd.isna(date_str):
        return None, None

    # 모든 날짜 패턴(yyyy.mm.dd, yyyy-mm-dd 등)을 찾아 리스트로 저장
    date_patterns = [
        r"\d{4}-\d{2}-\d{2}",
        r"\d{4}\.\d{2}\.\d{2}",
        r"\d{4}/\d{2}/\d{2}",
        r"\d{4}년\d{1,2}월\d{1,2}일",
        r"\d{4}년 \d{1,2}월 \d{1,2}일",
    ]
    
    dates = []
    for pattern in date_patterns:
        dates.extend(re.findall(pattern, date_str))

    if not dates:
        return None, None

    # 날짜 형식을 표준화
    parsed_dates = []
    for date in dates:
        for fmt in ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일"]:
            try:
                parsed_date = datetime.strptime(date, fmt)
                parsed_dates.append(parsed_date)
                break
            except:
                print(date)
                continue

    if not parsed_dates:
        return None, None

    # 가장 빠른 날짜와 가장 늦은 날짜 선택
    start_date = min(parsed_dates).strftime('%Y-%m-%d')
    end_date = max(parsed_dates).strftime('%Y-%m-%d')

    return start_date, end_date

def convert_csv_to_sqlite(csv_path, db_path):
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # 날짜 변환
    df[['시작일자', '종료일자']] = df['시작날짜/\n종료날짜'].apply(
        lambda x: pd.Series(parse_korean_date_range(str(x)))
    )

    conn = sqlite3.connect(db_path)

    # 기존 sw_data, sw_data_new 테이블 삭제
    conn.execute('DROP TABLE IF EXISTS sw_data')
    conn.execute('DROP TABLE IF EXISTS sw_data_new')

    # 임시로 DataFrame 데이터를 sw_data에 저장
    df.to_sql('sw_data', conn, index=False, if_exists='replace')

    # PRIMARY KEY 설정 위한 sw_data_new 테이블 생성
    columns_definition = ", ".join([f'"{col}" TEXT' for col in df.columns if col != '일련번호'])
    conn.execute(f'''
        CREATE TABLE sw_data_new (
            일련번호 INTEGER PRIMARY KEY,
            {columns_definition}
        );
    ''')

    # 특수 문자 처리 (컬럼 이름을 큰 따옴표로 감싸기)
    quoted_columns = ', '.join([f'"{col}"' for col in df.columns])

    # 데이터 옮기기
    conn.execute(f'''
        INSERT INTO sw_data_new({quoted_columns})
        SELECT {quoted_columns} FROM sw_data;
    ''')

    # 임시 테이블 삭제 후 이름 변경
    conn.execute('DROP TABLE sw_data;')
    conn.execute('ALTER TABLE sw_data_new RENAME TO sw_data;')

    conn.commit()
    conn.close()

    print(f"✅ CSV({csv_path}) → SQLite({db_path}) 변환 완료")
