# main/utils/ecmList

## 역할

Google Sheets의 시험완료 히스토리 데이터를 `main/data/ecmlist.db` 또는 지정한 SQLite DB의 `ecm_list` 테이블에 추가 동기화하는 수동 실행 유틸리티다.

## 파일

| 파일 | 설명 |
| --- | --- |
| `sync_sheets.py` | Google Sheets에서 신규 프로젝트를 읽어 `ecm_list`에 추가한다. 기존 `프로젝트번호`는 중복 삽입하지 않는다. |
| `requirements.txt` | 이 유틸리티 실행에 필요한 Google API 패키지 목록이다. |

## 로컬 인증 파일

아래 파일은 개인 인증 정보라 Git에 올리지 않는다.

- `credentials.json`
- `token.json`

## 읽는 Google Sheet 열

현재 스크립트는 `A`열 값이 `GS`인 행만 사용하며, 다음 열을 DB에 저장한다.

| Google Sheet 열 | 의미 | DB 컬럼 |
| --- | --- | --- |
| B | 프로젝트 번호 | `프로젝트번호` |
| C | 회사명 | `회사명` |
| D | 제품명 | `제품명` |
| F | WD | `WD` |
| L | 시험PL | `시험PL` |
| Q | 인증일자 | `인증일자` |

## 실행 메모

- 기본 DB 경로는 `main/data/ecmlist.db`다.
- Google Sheet ID는 `ECMLIST_SPREADSHEET_ID` 환경변수로 지정한다.
- 기본 시트 범위는 `'시험완료(히스토리)'!A2153:Q`다.
- 범위를 바꾸려면 `ECMLIST_SHEET_RANGE`를 지정한다.
- 다른 DB에 동기화하려면 `ECMLIST_DB_PATH`를 지정한다.
- 기존 `ecm_list` 테이블에 `WD` 컬럼이 없으면 자동으로 추가한다.
- 새 행의 산출물 점검 컬럼은 기본값 `X`로 생성된다.

## 실행 예시

```powershell
$env:ECMLIST_SPREADSHEET_ID="스프레드시트 ID"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```

영남 DB에 동기화하는 예시:

```powershell
$env:ECMLIST_SPREADSHEET_ID="스프레드시트 ID"
$env:ECMLIST_DB_PATH="C:\Users\jh910\Documents\New project 2\main\data\ecmlist2.db"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```
