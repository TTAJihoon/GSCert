"""
Google Sheets → SQLite 동기화 스크립트
- 구글시트 2153행~마지막 행에서 DB에 없는 프로젝트번호만 추가
- 수동 실행
"""

import sqlite3
import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# === 설정 ===
SPREADSHEET_ID = os.environ.get("ECMLIST_SPREADSHEET_ID", "").strip()
SHEET_RANGE = os.environ.get("ECMLIST_SHEET_RANGE", "'시험완료(히스토리)'!A2153:Q")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = Path(BASE_DIR).resolve().parents[2]
DB_PATH = os.environ.get("ECMLIST_DB_PATH", str(PROJECT_ROOT / "main" / "data" / "ecmlist.db"))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_credentials():
    """OAuth 인증 정보를 가져온다."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


def get_sheets_data():
    """구글시트 2153행~마지막 행에서 B, C, D, L, Q열 데이터를 가져온다."""
    if not SPREADSHEET_ID:
        raise RuntimeError("ECMLIST_SPREADSHEET_ID 환경변수를 설정해야 합니다.")

    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_RANGE,
    ).execute()

    rows = result.get("values", [])
    if not rows:
        print("시트에 데이터가 없습니다.")
        return []

    data = []
    for row in rows:
        def safe_get(idx):
            return row[idx].strip() if idx < len(row) and row[idx] else ""

        # A열이 'GS'인 행만 가져옴
        a_val = safe_get(0)
        if a_val != "GS":
            continue

        project_no = safe_get(1)  # B열
        if not project_no:
            continue

        data.append({
            "project_no": project_no,
            "company": safe_get(2),      # C열
            "product": safe_get(3),      # D열
            "tester": safe_get(11),      # L열
            "cert_date": safe_get(16),   # Q열 → 인증일자
        })

    return data


def get_existing_project_numbers():
    """DB에 이미 있는 프로젝트번호 목록을 가져온다."""
    if not os.path.exists(DB_PATH):
        return set()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 프로젝트번호 FROM ecm_list")
        existing = {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        existing = set()

    conn.close()
    return existing


def ensure_table():
    """테이블이 없으면 새 스키마로 생성한다. 기존 테이블이 있으면 유지."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ecm_list (
            번호 INTEGER PRIMARY KEY,
            인증일자 TEXT DEFAULT '',
            프로젝트번호 TEXT,
            회사명 TEXT,
            제품명 TEXT,
            시험PL TEXT,
            점검결과 TEXT DEFAULT 'X',
            계약서 TEXT DEFAULT 'X',
            "합의서(PDF)" TEXT DEFAULT 'X',
            수수료산정표 TEXT DEFAULT 'X',
            시험환경구성도 TEXT DEFAULT 'X',
            품질특성별제품정보기재사항 TEXT DEFAULT 'X',
            기능리스트 TEXT DEFAULT 'X',
            "시험계획서(PDF)" TEXT DEFAULT 'X',
            "점검표(PDF)" TEXT DEFAULT 'X',
            "최초/최종형상RawData" TEXT DEFAULT 'X',
            테스트케이스 TEXT DEFAULT 'X',
            결함리포트 TEXT DEFAULT 'X',
            "1차/2차/성능/보안RawData" TEXT DEFAULT 'X',
            "시험성적서(PDF)" TEXT DEFAULT 'X',
            시험기록서 TEXT DEFAULT 'X',
            품질평가보고서 TEXT DEFAULT 'X',
            품질검사표 TEXT DEFAULT 'X',
            SW저작권확인서 TEXT DEFAULT 'X',
            홍보이미지 TEXT DEFAULT 'X'
        )
    """)

    conn.commit()
    conn.close()


def sync_to_db(new_data):
    """DB에 없는 프로젝트번호만 추가한다. 번호는 빈 번호부터 순차 부여."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 현재 사용 중인 번호 목록 조회
    cursor.execute("SELECT 번호 FROM ecm_list ORDER BY 번호")
    used_numbers = {row[0] for row in cursor.fetchall()}

    # 1부터 순서대로 빈 번호를 찾아 부여
    next_num = 1
    inserted = 0
    for d in new_data:
        while next_num in used_numbers:
            next_num += 1
        cursor.execute(
            "INSERT INTO ecm_list (번호, 인증일자, 프로젝트번호, 회사명, 제품명, 시험PL) VALUES (?, ?, ?, ?, ?, ?)",
            (next_num, d["cert_date"], d["project_no"], d["company"], d["product"], d["tester"]),
        )
        used_numbers.add(next_num)
        next_num += 1
        inserted += 1

    conn.commit()
    conn.close()
    print(f"신규 {inserted}건 추가 완료 → {DB_PATH}")


def main():
    print("테이블 확인 중...")
    ensure_table()

    print("구글시트에서 데이터를 가져오는 중...")
    sheet_data = get_sheets_data()
    if not sheet_data:
        print("가져올 데이터가 없습니다.")
        return

    print(f"시트에서 {len(sheet_data)}건 읽음")

    # DB에 이미 있는 프로젝트번호 조회
    existing = get_existing_project_numbers()
    print(f"DB에 기존 {len(existing)}건 존재")

    # 중복 제거
    new_data = [d for d in sheet_data if d["project_no"] not in existing]
    print(f"신규 데이터: {len(new_data)}건")

    if new_data:
        sync_to_db(new_data)
    else:
        print("추가할 신규 데이터가 없습니다.")


if __name__ == "__main__":
    main()
