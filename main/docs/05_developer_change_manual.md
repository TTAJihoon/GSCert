# Download Review 개발 변경 매뉴얼

## 목적

이 문서는 기능을 바꿀 때 어디를 수정하고 어떤 검증을 해야 하는지 빠르게 찾기 위한 개발자용 안내서다.

## 변경 유형별 수정 위치

| 변경 내용 | 우선 확인 파일 |
| --- | --- |
| 프로젝트 목록/검색/기준정보 API | `main/views/review/ecm_download_review_jobs.py`, `main/views/review/ecm_reference_db.py`, `06_postgresql_api_access_manual.md` |
| PostgreSQL 기준정보/스키마 | `main/models.py`, `main/db_routers.py`, `13_db_schema.md` |
| Google Sheet -> `reference_project` 적재 | `main/management/commands/sync_reference_projects_from_sheet.py`, `10_reference_project_sheet_sync.md` |
| 작업 생성/취소/조회 API | `main/views/review/ecm_download_review_jobs.py` |
| worker 처리 | `main/views/review/ecm_download_review_worker.py`, `main/management/commands/run_download_worker.py` |
| 산출물 source | `main/views/review/artifact_source.py`, `11_artifact_source_boundary.md` |
| ECM HTTP 직접연동 | `main/views/review/ecm_http_client.py`, `12_http_ecm_source_decisions.md` |
| 점검 엔진 | `gscert_review_core.engine`, `main/views/review/ecm_download_review_inspection.py` |
| 점검규칙 기본값 | `main/management/commands/seed_download_review_rules.py` |
| 점검규칙 문서 | `03_inspection_rule_manual.md`, `09_rule_db_edit_quick_guide.md` |
| 결과 기대값/실제값/메시지 표시 | `gscert_review_core/result_display.py` |
| 화면/프론트 | `main/templates/`, `main/static/`, `main/views/review/ecm_download_review_jobs.py` |
| Windows 로컬 앱 | `local_review_app/`, `07_local_windows_app_test_manual.md`, `08_rulebase_shared_architecture.md` |
| LLM 점검 후보 | `main/views/review/ecm_llm_review.py`, `archive/2026-07-doc-cleanup/17_llm_review_interface.md` |

## 점검규칙을 추가하거나 바꿀 때

JSON 조건만 바꾸는 경우:

1. `03_inspection_rule_manual.md`에서 JSON 키와 가능한 범위를 확인한다.
2. `seed_download_review_rules.py`의 실제 규칙 정의를 수정한다.
3. `seed_download_review_rules --only-real --enable --update-existing --dry-run`으로 변경을 확인한다.
4. dry-run 결과가 맞으면 `--enable --update-existing`으로 반영한다.
5. `main.tests`에 샘플 케이스를 추가하거나 기존 케이스를 보강한다.
6. 실제 zip 또는 테스트 zip으로 결과를 확인한다.

새 검사 방식이 필요한 경우:

1. `gscert_review_core.engine`에 새 `rule_type` 또는 content check type을 추가한다.
2. 웹 어댑터와 Windows 로컬 runner가 같은 공용 엔진 경로를 쓰는지 확인한다.
3. 성공/실패 메시지와 `raw_detail_json` 증거를 함께 설계한다.
4. `03_inspection_rule_manual.md`에 새 타입을 문서화한다.
5. 새 `rule_type`은 Windows 앱 재배포가 필요한 변경인지 확인한다.

## 결과 표시를 바꿀 때

웹과 Windows 앱의 점검 결과 표시는 `gscert_review_core/result_display.py`를 공통 API로 사용한다.

수정 원칙:

1. 기대값/실제값/메시지 문구는 가능하면 `result_display.py`에서 한 번만 수정한다.
2. 웹 API는 `display_items`를 우선 내려준다.
3. Windows 앱은 공용 표시 row를 받아 같은 번호, 같은 기대값, 같은 실제값, 같은 메시지를 보여준다.
4. 표시 문구를 바꾸면 웹과 Windows 앱에서 같은 샘플 결과가 같은 문장으로 보이는지 확인한다.

## DB 컬럼이나 모델을 추가할 때

`13_db_schema.md`를 기준으로 어느 DB에 속하는지 먼저 정한다.

| DB | 변경 기준 |
| --- | --- |
| `reference` PostgreSQL | 공유 기준정보, 프로젝트, PL 매핑, 인증이력, 점검규칙 |
| `workflow` SQLite | 서버 로컬 작업, 프로젝트 처리 상태, 점검결과, 로그, lock |
| `default` SQLite | Django 기본 테이블, 레거시 `Job` |

확인할 것:

1. `main/models.py` 모델 위치.
2. `main/db_routers.py` 라우팅 대상.
3. `myproject/settings.py`의 `WORKFLOW_MODEL_NAMES` 또는 `REFERENCE_MODEL_NAMES`.
4. migration 대상 DB.
5. 관련 API serializer와 테스트.

## API나 UI를 바꿀 때

1. API 응답 필드가 바뀌면 테스트에서 JSON shape를 확인한다.
2. 프론트 화면 텍스트와 상태 라벨은 서버 serializer와 함께 맞춘다.
3. 결과 상세 표는 `display_items`와 `gscert_review_core/result_display.py`를 기준으로 한다.
4. 사용자에게 서버 절대 경로, 스택트레이스, 내부 screenshot 경로를 노출하지 않는다.

## worker나 자동화를 바꿀 때

1. source-specific 코드는 `ArtifactSource` 구현체에 둔다.
2. 워커, 검증, 점검, 상태 전이는 source 종류와 분리한다.
3. ECM HTTP는 `verify_ecm_http`로 실서버에서 확인한다.
4. 다운로드 파일 경로는 사용자에게 서버 절대 경로로 노출하지 않는다.

## 검증 명령

기본 검증:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
git diff --check
```

점검규칙 변경 검증:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

ECM HTTP 변경 검증:

```powershell
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center bundang --test-no <시험번호>
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center sangam --test-no <시험번호>
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center yeongnam --test-no <시험번호>
```

문서만 바꾼 경우:

```powershell
git diff --check
```

## 문서 갱신 체크리스트

| 바꾼 것 | 같이 갱신할 문서 |
| --- | --- |
| 현재 상태/다음 작업 | `00_next_step.md` |
| 점검규칙 JSON/새 rule type | `03_inspection_rule_manual.md`, `09_rule_db_edit_quick_guide.md` |
| 운영 명령/절차 | `04_download_review_operations_manual.md` |
| 코드 위치/검증 절차 | `05_developer_change_manual.md` |
| DB 구조 | `13_db_schema.md` |
| 기준정보/API 사용법 | `06_postgresql_api_access_manual.md` |
| Windows 앱 테스트/배포 | `07_local_windows_app_test_manual.md` |
| ECM source/HTTP 결정 | `11_artifact_source_boundary.md`, `12_http_ecm_source_decisions.md` |
| 남은 결정 사항 | `02_open_decisions.md` |

## 주의사항

- 사용자 또는 이전 작업자가 만든 변경을 되돌리지 않는다.
- `workflow.db`는 서버 로컬 실행 DB다. 커밋 대상이 아니다.
- `inspection_rule`은 공유 PostgreSQL `reference` DB에 있으므로 운영 직접 수정 전에는 백업/승인을 확인한다.
- 점검규칙은 가능하면 JSON으로 표현하고, 새 동작이 필요할 때만 검사 엔진 코드를 늘린다.
- 새 문서나 readme를 추가했으면 `01_manual_index.md`에서 찾을 수 있게 연결한다.
