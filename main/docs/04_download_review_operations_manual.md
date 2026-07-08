# Download Review 운영 매뉴얼

## 목적

이 문서는 `/download-review/` 기능을 실제로 실행하고 확인하는 절차를 정리한다. 설계 배경보다 “지금 무엇을 실행해야 하는지”에 초점을 둔다.

## 기본 URL

| 환경 | URL |
| --- | --- |
| 개발 PC | `http://127.0.0.1:8000/download-review/` |
| 운영 대표 서버 | `http://210.96.71.194/download-review/` |

194 서버가 download-review의 기준 진입점이다. 241 서버는 download-review 요청을 194로 넘기는 보조 경로로 본다.

## 서버 실행

개발 환경에서 Django 서버를 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

현재 테스트 편의를 위해 download-review 시간 제한은 `00:00-24:00`으로 열어둔 상태다. 운영 기준은 `20:00-07:00`이며, 관련 마커는 `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`다.

## worker 실행

dry-run으로 작업 상태 전이와 규칙 실행 경로를 먼저 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --once --dry-run --settings=myproject.ui_mock_settings
```

실제 ECM HTTP 직접연동으로 실행할 때는 `ecm-http` source를 사용한다.

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --live --source=ecm-http
```

환경변수 `DOWNLOAD_REVIEW_WORKER_CENTERS`가 비어 있으면 현재 서버가 허용하는 센터를 처리한다. 194 운영 기준에서는 분당·상암·영남 세 센터를 모두 처리한다.

## ECM HTTP 검증

실서버에서 센터별 로그인, 폴더 탐색, 다운로드 무결성을 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center bundang --test-no <시험번호>
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center sangam --test-no <시험번호>
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center yeongnam --test-no <시험번호>
```

실제 다운로드까지 확인하려면 `--download`를 붙인다.

```powershell
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center bundang --test-no <시험번호> --download
```

관련 문서:

- `12_http_ecm_source_decisions.md`
- `11_artifact_source_boundary.md`

## DB 기준

최신 DB 구조는 `13_db_schema.md`가 기준이다.

| DB | 용도 | 관리 기준 |
| --- | --- | --- |
| `reference` PostgreSQL | 프로젝트 기준정보, PL 매핑, 인증이력, 점검규칙 | 주 서버 공유 DB |
| `workflow` SQLite | 작업, 프로젝트 처리 상태, 점검결과, 로그, lock | 서버 로컬 실행 DB |
| `default` SQLite | Django 기본 테이블, 레거시 `Job` | 일반 Django DB |

주의:

- `inspection_rule`은 공유 PostgreSQL `reference` DB의 테이블이다.
- `inspection_result`는 서버 로컬 `workflow.db`의 테이블이다.
- 두 DB가 다르므로 결과는 `rule_code`/`rule_name` 문자열로 규칙을 식별한다.

## 기준 프로젝트 동기화

Google Sheet 프로젝트 목록을 PostgreSQL `reference_project`에 적재할 때는 `10_reference_project_sheet_sync.md`를 따른다.

```powershell
.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet --dry-run
```

실제 반영은 dry-run 결과를 확인한 뒤 수행한다.

## 점검규칙 seed

현재 실제 구현된 1~18번 규칙을 seed하려면 `--only-real`을 사용한다.

변경 내용 확인:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
```

실제 반영:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

규칙을 수정하려면 `03_inspection_rule_manual.md`와 `09_rule_db_edit_quick_guide.md`를 먼저 본다.

## 샘플 zip 검증

샘플 zip 또는 실제 ECM 다운로드 결과로 1~18번 전체 규칙을 확인한다.

최근 기준으로 웹과 Windows 앱은 같은 공용 엔진을 사용하므로, 같은 프로젝트 기준정보와 같은 산출물 입력을 넣으면 기대값/실제값/메시지도 같은 표시 API를 통해 제공되어야 한다.

관련 코드:

- `gscert_review_core.engine`
- `gscert_review_core/result_display.py`
- `main/views/review/ecm_download_review_jobs.py`
- `local_review_app/gscert_local_review/app_dashboard.py`

## 기본 검증 명령

코드 또는 규칙 변경 후 아래 명령을 우선 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

문서만 바꾼 경우에도 `git diff --check`는 실행한다.

## 운영 중 확인할 항목

| 증상 | 확인 위치 |
| --- | --- |
| 프로젝트가 목록에 안 보임 | `reference_project`, `/api/projects/`, `06_postgresql_api_access_manual.md` |
| 기준정보 날짜가 비어 있음 | `reference_project` 일정 컬럼, `/api/local-review/projects/{project_number}/metadata/` |
| 작업이 시작되지 않음 | 시간 제한, active job 수, `workflow.db` job 상태 |
| worker가 멈춘 것 같음 | heartbeat, `automation_lock`, worker process |
| ECM 다운로드가 실패함 | `verify_ecm_http`, `12_http_ecm_source_decisions.md` |
| 파일은 있는데 규칙이 실패함 | `inspection_result.raw_detail_json`, `03_inspection_rule_manual.md` |
| UI 결과 문구가 이상함 | `gscert_review_core/result_display.py`, `/api/job-projects/{id}/results/` |

## 백업 기준

`workflow.db`를 직접 만지기 전에는 백업한다.

```powershell
Copy-Item main\data\workflow.db "main\data\workflow.db.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

PostgreSQL `reference` DB는 운영 공유 DB이므로 직접 수정 전에 dump 또는 관리 도구 백업 절차를 따른다.

## 다음 운영 체크포인트

1. 센터별 `verify_ecm_http --download` 실측을 완료한다.
2. 194 서버 worker가 `--source=ecm-http`로 세 센터 작업을 처리하는지 확인한다.
3. 샘플 zip 또는 실제 정상 산출물로 1~18번 전체 PASS 여부를 확인한다.
4. 테스트가 끝나면 download-review 시간 제한을 `20:00-07:00`으로 되돌린다.
