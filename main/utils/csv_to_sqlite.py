import pandas as pd
import sqlite3
from datetime import datetime
from tqdm import tqdm

csv_path = './data/reference.csv'
db_path = './data/reference.sqlite3'

# 날짜 전처리 함수
def parse_korean_date_range(date_range_str):
    if pd.isna(date_range_str) or '~' not in date_range_str:
        return None, None
    start_str, end_str = date_range_str.split('~')
    date_formats = ["%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y년 %m월 %d일"]
    
    def parse_date(date_str):
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d')
            except:
                continue
        return None

    return parse_date(start_str), parse_date(end_str)

# 데이터 로드 및 전처리
df = pd.read_csv(csv_path)
df.columns = df.columns.str.strip()

# 날짜 컬럼 변환
df[['시작일자', '종료일자']] = df['시작날짜/\n종료날짜'].apply(
    lambda x: pd.Series(parse_korean_date_range(str(x)))
)

# SQLite DB 연결 및 데이터 저장
conn = sqlite3.connect(db_path)

# 기존 테이블 삭제(필요 시)
conn.execute('DROP TABLE IF EXISTS sw_data')

# 데이터프레임 SQLite로 저장
df.to_sql('sw_data', conn, index=False, if_exists='replace')

# '일련번호' 컬럼을 기본키로 지정하고 인덱싱 추가
conn.execute('''
    CREATE UNIQUE INDEX idx_sw_data_id ON sw_data(일련번호);
''')

conn.commit()
conn.close()

print("✅ SQLite 데이터 저장 완료")
