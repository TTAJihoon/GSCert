"""로컬 점검 앱 '직접 입력' 보강용 구글시트 조회.

reference_project(인증위 목록 DB)와 reference.xlsx 어디에서도 프로젝트를 찾지 못했을 때
마지막으로 시도하는 온라인 보강 경로다. main/utils/ecmList/sync_sheets.py가 이미 쓰고
있는 OAuth 자격증명(credentials.json, token.json)을 그대로 재사용한다 — 그 인증을
완료한 계정이 아래 시트들도 조회 권한을 갖고 있어 별도 설정 없이 바로 동작한다.

시트 구조(공통): A열 'GS' 표시가 있는 행만 실제 프로젝트 데이터이고, 그 사이사이에
섹션 제목/재헤더 행이 섞여 있다(main/utils/ecm_reference_sheet.py의 인증위 시트와 같은
패턴). B=프로젝트번호, C=회사명, D=제품명, F=WD, H=신청일, I=계약일, J=시험 시작일,
K=시험 종료일, L=시험원(','로 구분된 이름들 중 첫 번째가 시험PL).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


_CREDENTIALS_DIR = Path(__file__).resolve().parent / "ecmList"
CREDENTIALS_PATH = _CREDENTIALS_DIR / "credentials.json"
TOKEN_PATH = _CREDENTIALS_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# 2, 3번째 시트는 아직 미정이라 자리만 준비해둔다. spreadsheet_id/tab_name이 정해지면
# 이 목록에 추가하는 것만으로 조회 대상에 포함된다(코드 변경 불필요).
SOURCES: list[dict[str, str]] = [
    {
        "name": "상암 시험 진행 현황",
        "spreadsheet_id": "1oQdg4o3jISUaZhChLNfhqd52SZAlGNrgQUrzyLxD2Qw",
        "tab_name": "시험 진행",
    },
]

# 시트 전체를 한 번의 API 호출로 읽어와 짧게 캐시한다 — 같은 시트를 매 조회마다 다시
# 내려받지 않아도 되고, API 쿼터도 아낀다.
_CACHE_TTL_SECONDS = 300
_row_cache: dict[str, tuple[float, list[list[str]]]] = {}


class GoogleSheetLookupError(RuntimeError):
    pass


def _get_credentials() -> Credentials:
    if not TOKEN_PATH.is_file():
        raise GoogleSheetLookupError(f"Google OAuth 토큰이 없습니다: {TOKEN_PATH}")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.valid:
        return creds
    if not (creds.expired and creds.refresh_token):
        raise GoogleSheetLookupError("Google OAuth 토큰을 갱신할 수 없습니다. token.json을 다시 발급해야 합니다.")
    creds.refresh(Request())
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _fetch_rows(spreadsheet_id: str, tab_name: str) -> list[list[str]]:
    cache_key = f"{spreadsheet_id}!{tab_name}"
    cached = _row_cache.get(cache_key)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"'{tab_name}'!A:L")
            .execute()
        )
    except HttpError as exc:
        raise GoogleSheetLookupError(f"구글시트 조회 실패({spreadsheet_id}): {exc}") from exc

    rows = result.get("values", [])
    _row_cache[cache_key] = (now, rows)
    return rows


def _cell(row: list[Any], index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _find_in_rows(rows: list[list[str]], project_number: str) -> dict[str, str] | None:
    target = project_number.strip().upper()
    for row in rows:
        if _cell(row, 0).upper() != "GS":
            continue
        if _cell(row, 1).upper() != target:
            continue
        tester = _cell(row, 11)
        pl_name = tester.split(",", 1)[0].strip() if tester else ""
        return {
            "company_name": _cell(row, 2),
            "product_name": _cell(row, 3),
            "wd_name": _cell(row, 5),
            "request_date": _cell(row, 7),
            "contract_date": _cell(row, 8),
            "start_date": _cell(row, 9),
            "end_date": _cell(row, 10),
            "pl_name": pl_name,
        }
    return None


def lookup_project(project_number: str) -> dict[str, str] | None:
    """등록된 구글시트를 순서대로 조회해 프로젝트번호가 일치하는 첫 결과를 반환한다.

    개별 시트 조회가 실패해도(권한 변경, 일시 오류 등) 나머지 시트는 계속 시도한다.
    """
    project_number = (project_number or "").strip()
    if not project_number:
        return None
    for source in SOURCES:
        try:
            rows = _fetch_rows(source["spreadsheet_id"], source["tab_name"])
        except GoogleSheetLookupError:
            continue
        match = _find_in_rows(rows, project_number)
        if match is not None:
            match["source"] = source["name"]
            return match
    return None
