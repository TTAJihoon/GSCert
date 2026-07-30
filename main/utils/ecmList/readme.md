# main/utils/ecmList

## 역할

Google Sheets의 시험완료 히스토리 데이터를 PostgreSQL `reference_project` 테이블에 추가 동기화하는 수동 실행 유틸리티다.

일상 운영에서는 `main/docs/10_reference_project_sheet_sync.md`의 관리 명령 `sync_reference_projects_from_sheet`를 우선 사용한다. 이 폴더의 `sync_sheets.py`는 OAuth 인증 파일을 직접 사용하는 보조 스크립트다.

## 파일

| 파일 | 설명 |
| --- | --- |
| `sync_sheets.py` | Google Sheets에서 신규 프로젝트를 읽어 `reference_project`에 upsert한다. 기존 `project_number`는 중복 삽입하지 않고 원천 메타데이터만 갱신한다. |
| `requirements.txt` | 이 유틸리티 실행에 필요한 Google API 패키지 목록이다. |

## 로컬 인증 파일

아래 파일은 개인 인증 정보라 Git에 올리지 않는다.

- `credentials.json`
- `token.json`

## 읽는 Google Sheet 열

현재 스크립트는 `A`열 값이 `GS`인 행만 사용하며, 다음 열을 DB에 저장한다.

| Google Sheet 열 | 의미 | `ReferenceProject` 필드 |
| --- | --- | --- |
| B | 프로젝트 번호 | `project_number` |
| C | 회사명 | `company` |
| D | 제품명 | `product` |
| F | WD | `wd` |
| H | 신청일 | `request_date` |
| I | 계약일 | `contract_date` |
| L | 시험PL | `primary_tester`, `pl` |
| Q | 인증일자 | `cert_date` |

## 실행 메모

- Google Sheet ID는 `ECMLIST_SPREADSHEET_ID` 환경변수로 지정한다.
- 기본 시트 범위는 `'시험완료(히스토리)'!A2153:Q`다.
- 범위를 바꾸려면 `ECMLIST_SHEET_RANGE`를 지정한다.
- 센터는 `ECMLIST_CENTER`로 지정하며 기본값은 `sangam`이다.
- DB alias는 `ECMLIST_DB_ALIAS`로 지정하며 기본값은 Django 설정의 `REFERENCE_DATABASE_ALIAS`다.

## 실행 예시

```powershell
$env:ECMLIST_SPREADSHEET_ID="스프레드시트 ID"
$env:ECMLIST_CENTER="sangam"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```

영남 프로젝트로 적재하는 예시:

```powershell
$env:ECMLIST_SPREADSHEET_ID="스프레드시트 ID"
$env:ECMLIST_CENTER="yeongnam"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```
