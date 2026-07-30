# GSCert 문서 목차와 사용 가이드

## 목적

이 문서는 `main/docs`의 입구다. 운영자, 개발자, 규칙 수정자가 어떤 문서를 먼저 봐야 하는지 빠르게 안내한다.

2026-07 문서 정리 이후 루트에는 현재 사용하는 문서만 남겼다. 과거 설계 원문과 진행 로그는 `archive/2026-07-doc-cleanup/` 아래에 보관한다.

## 먼저 어디를 볼까

| 상황 | 먼저 볼 문서 | 이어서 볼 문서 |
| --- | --- | --- |
| 다른 PC에서 바로 이어받기 | `00_next_step.md` | `04_download_review_operations_manual.md` |
| 전체 문서 지도를 확인하기 | `readme.md` | 이 문서 |
| 남은 결정 사항 확인 | `02_open_decisions.md` | `00_next_step.md` |
| 최근 완료된 변경 확인 | `14_completed_download_review_changes.md` | `00_next_step.md` |
| 점검규칙을 수정하기 | `09_rule_db_edit_quick_guide.md` | `03_inspection_rule_manual.md`, `08_rulebase_shared_architecture.md` |
| 점검 결과 기대값/실제값/메시지 표시를 수정하기 | `05_developer_change_manual.md` | `gscert_review_core/result_display.py`, `03_inspection_rule_manual.md` |
| 서버/worker를 실행하기 | `04_download_review_operations_manual.md` | `11_artifact_source_boundary.md`, `12_http_ecm_source_decisions.md` |
| PostgreSQL/API 구조를 확인하기 | `13_db_schema.md` | `06_postgresql_api_access_manual.md`, `10_reference_project_sheet_sync.md` |
| Windows 로컬 앱을 테스트하기 | `07_local_windows_app_test_manual.md` | `06_postgresql_api_access_manual.md`, `08_rulebase_shared_architecture.md` |
| ECM HTTP 직접연동을 확인하기 | `12_http_ecm_source_decisions.md` | `11_artifact_source_boundary.md` |
| 과거 Playwright/agent 설계 원문을 찾기 | `archive/2026-07-doc-cleanup/readme.md` | archive 안의 원문 |

## 현재 문서 지도

### 1. 인수인계와 결정

- `00_next_step.md`: 현재 브랜치, 최신 구조, 바로 다음 작업.
- `02_open_decisions.md`: 아직 확정하거나 실측해야 할 결정 항목.
- `14_completed_download_review_changes.md`: 최근 완료된 UI/DB/규칙 변경의 이력성 요약.
- `01_manual_index.md`: 지금 보고 있는 문서.
- `readme.md`: `main/docs` 폴더의 짧은 안내.

### 2. 점검규칙과 결과 표시

- `03_inspection_rule_manual.md`: 1~18번 점검규칙의 단일 기준 문서.
- `08_rulebase_shared_architecture.md`: 웹과 Windows 앱이 같은 규칙 DB/API/공용 엔진을 쓰는 구조.
- `09_rule_db_edit_quick_guide.md`: `inspection_rule`을 수정하는 실무 절차.
- `gscert_review_core/result_display.py`: 웹과 Windows 앱이 공유하는 결과 표시 API.

현재 실제 점검규칙은 1~18번이 구현되어 있으며, `seed_download_review_rules --only-real --enable --update-existing` 기준으로 반영한다. 화면의 세부 점검 항목 번호는 `1-1`, `1-2`, ..., `18-1` 형식을 사용한다.

### 3. 운영과 DB

- `04_download_review_operations_manual.md`: 서버/worker 실행, ECM HTTP 검증, seed, 테스트 명령.
- `06_postgresql_api_access_manual.md`: 외부 PC와 Windows 앱이 API로 기준정보를 조회하는 방법.
- `07_local_windows_app_test_manual.md`: 로컬 Windows 앱 설치, 실행, 패키징, self-check.
- `10_reference_project_sheet_sync.md`: Google Sheet 프로젝트 목록을 PostgreSQL `reference_project`에 적재하는 방법.
- `13_db_schema.md`: `default`, `workflow`, `reference` DB와 테이블 구조.

운영 기준 DB는 다음처럼 본다.

| DB | 역할 |
| --- | --- |
| `reference` PostgreSQL | 공유 기준정보, 프로젝트 목록, PL 매핑, 인증이력, 점검규칙, 수동 적합 메모 |
| `workflow` SQLite | 서버 로컬 작업, 프로젝트 처리 상태, 점검결과, 로그, lock, 유사 분석 작업 |
| `default` SQLite | Django 기본 테이블과 레거시 `Job` |

### 4. ECM/source 경계

- `11_artifact_source_boundary.md`: `ecm`, `ecm-http`, `local` source의 책임 경계.
- `12_http_ecm_source_decisions.md`: ECM 다운로드 HTTP 직접연동 전환 결정과 검증 절차.

현재 download-review는 194 서버가 `ecm-http` source로 분당·상암·영남을 모두 처리하는 구조를 기준으로 한다. 241 서버는 download-review 진입을 194로 넘기는 보조 경로로 본다.

### 5. Archive

아래 문서는 현재 루트에서 제외하고 archive에 보관했다.

```text
main/docs/archive/2026-07-doc-cleanup/
```

대표적인 보관 문서:

| 과거 문서 | 현재 먼저 볼 문서 |
| --- | --- |
| `01_automation_flow.md`, `12_implementation_roadmap.md`, `16_*` | `00_next_step.md`, `02_open_decisions.md` |
| `02_database_design.md` | `13_db_schema.md` |
| `03_webpage1_automation.md`, `04_agent_download.md`, `30_*`, `31_*`, `32_ecm_integration_reference.md` | `11_artifact_source_boundary.md`, `12_http_ecm_source_decisions.md` |
| `05_zip_inspection.md`, `22_expected_value_display_mapping.md` | `03_inspection_rule_manual.md`, `gscert_review_core/result_display.py` |
| `08_ui_api_design.md`, `13_ui_mockup_design.md` | `05_developer_change_manual.md` |
| `10_operations_scripts.md`, `14_dependency_management.md` | `04_download_review_operations_manual.md` |
| `23_local_desktop_postgresql_design.md`, `32_google_sheet_reference_project_postgres_sync.md` | `06_postgresql_api_access_manual.md`, `10_reference_project_sheet_sync.md`, `13_db_schema.md` |

## 문서 유지 원칙

- 새 기능은 관련 코드와 함께 사용자가 실제로 볼 문서에도 반영한다.
- 설계 배경은 archive에 둘 수 있지만, 운영/개발자가 따라야 하는 최신 절차는 루트 문서에 남긴다.
- 같은 설명을 여러 문서에 길게 복사하지 않는다. 자세한 기준 문서 하나를 정하고 다른 문서는 링크만 둔다.
- 문서만 수정해도 `git diff --check`로 공백 오류를 확인한다.
