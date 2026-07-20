import sqlite3

import pandas as pd

# 날짜 파싱은 xlsx 변환 경로와 동일한 구현을 재사용한다(사본 중복 방지).
from main.utils.xlsx_to_sqlite import parse_korean_date_range

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
