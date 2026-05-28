# Download Review 운영 매뉴얼

## 목적

이 문서는 `/download-review/` 기능을 실제로 실행하고 확인하는 절차를 정리한다. 설계 배경보다 “지금 무엇을 실행해야 하는지”에 초점을 둔다.

## 기본 URL

| 화면 | URL |
| --- | --- |
| 보안 페이지 | `http://127.0.0.1:8000/security/` |
| 다운로드 검토 페이지 | `http://127.0.0.1:8000/download-review/` |

## 서버 실행

개발 환경에서 Django 서버를 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

현재 테스트 편의를 위해 download-review 시간 제한은 `00:00-24:00`으로 열어둔 상태다. 운영 기준은 `20:00-07:00`이며, 관련 마커는 `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`다.

## worker 실행

worker 설계와 운영 스크립트는 다음 문서를 기준으로 한다.

| 목적 | 문서 |
| --- | --- |
| worker 처리 흐름 | `09_worker_process_design.md` |
| PowerShell 운영 스크립트 | `10_operations_scripts.md` |
| lock과 복구 | `06_recovery_and_lock.md` |

개발 검증은 보통 테스트 명령과 dry-run worker부터 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --once --dry-run --settings=myproject.ui_mock_settings
```

실제 ECM/agent 다운로드를 붙일 때는 ECM 로그인 상태, Windows agent, 다운로드 폴더 권한, 공통 lock 상태를 함께 확인한다.

## 기준 프로젝트 DB

download-review가 프로젝트 목록을 읽는 DB는 센터별로 나뉜다.

| DB | 용도 |
| --- | --- |
| `main/data/ecmlist.db` | 상암 기준 프로젝트 목록 |
| `main/data/ecmlist2.db` | 영남 기준 프로젝트 목록 |

`workflow.db`는 작업, worker, 점검규칙, 점검결과가 들어가는 로컬 실행 DB다.

| DB | Git 정책 |
| --- | --- |
| `ecmlist.db`, `ecmlist2.db` | 기준 데이터로 관리 대상 |
| `workflow.db` | 로컬 실행 산출물이므로 Git 제외 |

## Google Sheet 동기화

동기화 도구는 `main/utils/ecmList/sync_sheets.py`다.

현재 Google Sheet에서 읽는 열은 다음과 같다.

| Google Sheet 열 | DB 컬럼 |
| --- | --- |
| B | `프로젝트번호` |
| C | `회사명` |
| D | `제품명` |
| F | `WD` |
| L | `시험PL` |
| Q | `인증일자` |

`A`열 값이 `GS`인 행만 가져오며, 이미 DB에 있는 `프로젝트번호`는 중복 삽입하지 않는다. 기존 `ecm_list` 테이블에 `WD` 컬럼이 없으면 자동으로 추가한다.

필수 환경변수는 다음과 같다.

| 변수 | 설명 |
| --- | --- |
| `ECMLIST_SPREADSHEET_ID` | Google Sheet ID |
| `ECMLIST_SHEET_RANGE` | 선택. 기본값은 `'시험완료(히스토리)'!A2153:Q` |
| `ECMLIST_DB_PATH` | 선택. 기본값은 `main/data/ecmlist.db` |

실행 예시는 다음과 같다.

```powershell
$env:ECMLIST_SPREADSHEET_ID="스프레드시트 ID"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```

다른 DB에 동기화하려면 `ECMLIST_DB_PATH`를 지정한다.

```powershell
$env:ECMLIST_DB_PATH="C:\Users\jh910\Documents\New project 2\main\data\ecmlist2.db"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```

## 점검규칙 seed

현재 실제 구현된 규칙 1~5번만 seed하려면 `--only-real`을 사용한다.

변경 내용 확인:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
```

실제 반영:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

점검규칙 JSON을 수정하려면 `19_inspection_rule_manual.md`를 먼저 본다.

## 샘플 zip 검증

테스트 대상 zip은 `C:\test` 경로에 두고, 프로젝트 번호는 `TTA-26-00266`을 기준으로 검증한다.

현재 검증된 결과는 다음과 같다.

| 산출물 | 결과 |
| --- | --- |
| 계약서 | `O` |
| 합의서(PDF) | `O` |
| 수수료산정표 | `O` |
| 시험환경구성도 | `O` |
| 품질특성별제품정보기재사항 | `O` |

6번 기능리스트와 7번 시험계획서(PDF)는 다음 구현 대상이다.

## 기본 검증 명령

코드 또는 규칙 변경 후 아래 명령을 우선 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

문서만 바꾼 경우에도 `git diff --check`는 실행한다.

## 운영 중 확인할 항목

| 증상 | 확인 위치 |
| --- | --- |
| 프로젝트가 목록에 안 보임 | `ecmlist.db`/`ecmlist2.db`, `main/views/review/ecm_reference_db.py` |
| WD 값이 비어 있음 | Google Sheet F열, `sync_sheets.py`, `ecm_list.WD` |
| 작업이 시작되지 않음 | 시간 제한, active job 수, `workflow.db` job 상태 |
| worker가 멈춘 것 같음 | heartbeat, `automation_lock`, worker process |
| 파일은 있는데 규칙이 실패함 | `inspection_result.raw_detail_json`, `19_inspection_rule_manual.md` |
| UI 결과가 이상함 | `08_ui_api_design.md`, `/api/job-projects/{id}/results/` |

## 백업 기준

규칙이나 작업 이력이 들어 있는 `workflow.db`를 직접 만지기 전에는 백업한다.

```powershell
Copy-Item main\data\workflow.db "main\data\workflow.db.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

`ecmlist.db`와 `ecmlist2.db`는 기준 데이터 파일이다. 동기화나 컬럼 변경 후에는 의도한 변경인지 확인하고 커밋 대상에 포함한다.

## 다음 운영 체크포인트

1. `WD` 값이 실제 Google Sheet F열에서 안정적으로 들어오는지 한 번 더 동기화 검증한다.
2. 6번 기능리스트 구현 전 `.xls` 샘플 처리 의존성을 결정한다.
3. 6~7번 규칙 구현 후 `C:\test` 샘플 zip으로 다시 전체 검증한다.
4. 테스트가 끝나면 download-review 시간 제한을 운영 기준인 `20:00-07:00`으로 되돌린다.
