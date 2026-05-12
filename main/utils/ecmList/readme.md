# main/utils/ecmList

## 역할

Google Sheets의 시험완료 히스토리 데이터를 `main/data/ecmlist.db`의 `ecm_list` 테이블에 추가 동기화하는 수동 실행 유틸리티다.

## 파일

| 파일 | 설명 |
| --- | --- |
| `sync_sheets.py` | Google Sheets에서 신규 프로젝트를 읽어 `ecm_list`에 추가한다. 기존 프로젝트번호는 중복 삽입하지 않는다. |
| `requirements.txt` | 이 유틸리티 실행에 필요한 Google API 패키지 목록이다. |

## 로컬 파일

아래 파일은 개인 인증 정보이므로 Git에 올리지 않는다.

- `credentials.json`
- `token.json`

## 실행 메모

- 기본 DB 경로는 `main/data/ecmlist.db`다.
- Google Sheet ID는 `ECMLIST_SPREADSHEET_ID` 환경변수로 지정한다.
- 시트 범위는 기본값으로 `'시험완료(히스토리)'!A2153:Q`를 사용하며, 필요하면 `ECMLIST_SHEET_RANGE`로 변경한다.
- 다른 DB에 동기화해야 하면 `ECMLIST_DB_PATH` 환경변수로 경로를 지정한다.
- `번호`부터 `시험PL`까지의 기준정보만 신규 행으로 추가한다.
- `점검결과`부터 `홍보이미지`까지의 점검 컬럼은 기본값 `X`로 생성한다.
