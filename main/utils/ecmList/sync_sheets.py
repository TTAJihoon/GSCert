"""
Google Sheets → PostgreSQL reference_project 동기화 스크립트
- 구글시트 2153행~마지막 행에서 데이터를 읽어 reference_project 테이블에 upsert
- 신규 프로젝트는 추가, 기존 프로젝트는 원천 메타데이터(회사명, 제품명 등)만 갱신
- 수동 실행
"""

import os
import sys
from pathlib import Path

# 독립 실행 시 Django 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

import django
django.setup()

from django.conf import settings

from main.models import ReferenceProject
from main.views.review.ecm_download_review_centers import center_label, normalize_center_code

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# === 설정 ===
SPREADSHEET_ID = os.environ.get("ECMLIST_SPREADSHEET_ID", "").strip()
SHEET_RANGE = os.environ.get("ECMLIST_SHEET_RANGE", "'시험완료(히스토리)'!A2153:Q")
CENTER_CODE = normalize_center_code(os.environ.get("ECMLIST_CENTER", "sangam"))
DB_ALIAS = os.environ.get(
    "ECMLIST_DB_ALIAS",
    getattr(settings, "REFERENCE_DATABASE_ALIAS", "reference"),
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
    """구글시트 2153행~마지막 행에서 B, C, D, F, H, I, L, Q열 데이터를 가져온다."""
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
            "company": safe_get(2),       # C열
            "product": safe_get(3),       # D열
            "wd": safe_get(5),            # F열
            "request_date": safe_get(7),  # H열 → 신청일
            "contract_date": safe_get(8), # I열 → 계약일
            "tester": safe_get(11),       # L열
            "cert_date": safe_get(16),    # Q열 → 인증일자
        })

    return data


def get_existing_project_numbers():
    """DB에 이미 있는 프로젝트번호 목록을 가져온다."""
    return set(
        ReferenceProject.objects.using(DB_ALIAS)
        .filter(center_code=CENTER_CODE)
        .values_list("project_number", flat=True)
    )


def sync_to_db(new_data):
    """DB에 없는 프로젝트번호를 추가하고 기존 프로젝트의 원천 메타데이터를 갱신한다."""
    label = center_label(CENTER_CODE)
    inserted = updated = 0

    for d in new_data:
        metadata = {
            "center_label": label,
            "cert_date": d["cert_date"],
            "company": d["company"],
            "product": d["product"],
            "pl": d["tester"],
            "wd": d["wd"],
            "request_date": d["request_date"],
            "contract_date": d["contract_date"],
        }
        _, is_created = ReferenceProject.objects.using(DB_ALIAS).update_or_create(
            project_number=d["project_no"],
            center_code=CENTER_CODE,
            defaults=metadata,
        )
        if is_created:
            inserted += 1
        else:
            updated += 1

    print(f"신규 {inserted}건 추가, 기존 {updated}건 원천 메타데이터 갱신 완료 → PostgreSQL ({DB_ALIAS})")


def main():
    print(f"센터: {CENTER_CODE} / DB alias: {DB_ALIAS}")
    print("구글시트에서 데이터를 가져오는 중...")
    sheet_data = get_sheets_data()
    if not sheet_data:
        print("가져올 데이터가 없습니다.")
        return

    print(f"시트에서 {len(sheet_data)}건 읽음")

    existing = get_existing_project_numbers()
    print(f"DB에 기존 {len(existing)}건 존재")

    sync_to_db(sheet_data)


if __name__ == "__main__":
    main()
