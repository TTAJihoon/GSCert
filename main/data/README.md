# main/data Git Policy

서버 실행에 필요한 기준 데이터는 Git에 포함하고, 실행 중 계속 바뀌는 상태 파일은 제외한다.

## Git 포함

- `ecmlist.db`: download-review 상암 프로젝트 목록과 점검 결과 기준 DB
- `ecmlist2.db`: download-review 영남 프로젝트 목록과 점검 결과 기준 DB
- `reference.db`: 기존 이력/제품정보 조회 화면에서 사용하는 SQLite DB
- `reference.xlsx`: ECM에서 내려받아 누적 관리하는 기준 원본 데이터
- `prdinfo.xlsx`: 제품정보 양식 원본
- `security.xlsx`: 보안 취약점 매핑 데이터

`ecmlist.db`와 `ecmlist2.db`의 `WD` 컬럼은 Google Sheet F열에서 가져온다.
신규 프로젝트 추가는 `main/utils/ecmList/sync_sheets.py`를 수동 실행해서 반영한다.

`reference.db`는 아래 명령으로 `reference.xlsx`에서 재생성할 수 있다. 기본 실행은 DB 생성 후
`reference.xlsx`와 `reference.db` 변경분을 Git commit/push까지 수행한다.

이 명령은 실행될 때만 동작한다. 별도 스케줄러를 만들지 않았으며, 운영에서는 기존처럼
`weekly.py` 또는 배치 파일이 이 흐름을 시작한다. 현재 `weekly.py`는 ECM 원천 데이터를
`reference.xlsx`에 반영한 뒤 `manage.py sqlite --force`를 직접 호출한다.
`weekly.py`는 기본적으로 프로젝트의 `.venv\Scripts\python.exe`, `venv\Scripts\python.exe`,
상위 폴더의 `.venv`/`venv`를 찾아 `manage.py sqlite`를 실행한다. 다른 Python을 강제로 쓰려면
`GSCERT_PYTHON`을 지정한다.

```powershell
.\.venv\Scripts\python.exe manage.py sqlite
```

로컬 검증만 하고 Git 반영을 생략하려면 아래처럼 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py sqlite --no-git-sync
```

특정 주차 파일을 강제로 반영해야 하면 `weekly.py` 실행 전에 대상 월요일을 지정한다.

```powershell
$env:GSCERT_WEEKLY_TARGET_DATE = "20260511"
.\.venv\Scripts\python.exe main\utils\weekly.py
```

또는 `weekly.py`의 첫 번째 인자로 대상 날짜를 바로 전달한다. 이 값은 환경변수보다 우선하며,
ECM에서 클릭할 문서명과 연도 폴더 선택에도 사용된다.

```powershell
.\.venv\Scripts\python.exe main\utils\weekly.py 20260608
```

DB 적재가 정상 실행되면 `main/data/weekly_gs_sync.log`에 아래 흐름이 남는다.
weekly 흐름은 `ECM 다운로드 -> reference.xlsx 업데이트 -> reference.db 업데이트`만 수행하며
서버 종료/시작용 `exit.bat`/`run.bat`는 호출하지 않는다.

```text
reference DB 적재 실행: ... manage.py sqlite ... reference.xlsx ... reference.db ...
reference DB 갱신 확인: ... reference.db size=... updated_at=...
```

`reference.xlsx`만 갱신되고 `reference.db`가 갱신되지 않으면 `weekly_gs_sync.log`의
`reference DB 적재 stderr` 또는 `UNHANDLED ERROR` 항목을 먼저 확인한다.

이미 내려받은 xlsx를 바로 기준 파일에 반영해야 하면 다운로드 단계를 생략할 수 있다.

```powershell
$env:GSCERT_WEEKLY_SOURCE_XLSX = "C:\Users\jh910\Downloads\Telegram Desktop\인증획득제품(20260511).xlsx"
.\.venv\Scripts\python.exe main\utils\weekly.py
```

## Git 제외

- `workflow.db`: 작업 요청, 대기열, 진행상태, 로그 등 실행 이력 DB
- `ecm_agent.lock`: ECM/agent 동시 접근 방지용 로컬 잠금 파일
- `faiss_bge_m3_ko.idmap.index`, `ngram_table.npz`: 유틸리티가 생성하는 검색 인덱스

FAISS 임베딩 인덱스는 아래 명령으로 갱신한다. 기본 동작은 기존 인덱스의 `일련번호`를
확인한 뒤 DB에 추가된 신규 행만 임베딩해서 붙인다.

```powershell
.\.venv\Scripts\python.exe manage.py embed_db main\data\reference.db
```

기존 행의 내용이 수정되었거나 모델/인덱스 구조를 바꾼 경우에는 전체 재생성을 명시한다.

```powershell
.\.venv\Scripts\python.exe manage.py embed_db main\data\reference.db --rebuild
```
