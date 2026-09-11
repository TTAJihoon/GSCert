# 개발자 가이드

## 목적

기능을 바꿀 때 어디를 수정하고 어떤 검증을 해야 하는지 빠르게 찾기 위한 개발자용 안내서다. 뒷부분에는 규칙 정의와 실행 엔진이 어떻게 분리돼 있는지, 그래서 무엇을 바꿀 때 어디를 다시 배포해야 하는지를 정리했다.

## 변경 유형별 수정 위치

| 변경 내용 | 우선 확인 파일 |
| --- | --- |
| 프로젝트 목록/검색/기준정보 API | `main/views/review/ecm_download_review_jobs.py`, `main/views/review/ecm_reference_db.py`, `04_data_and_api.md` |
| PostgreSQL 기준정보/스키마 | `main/models.py`, `main/db_routers.py`, `04_data_and_api.md` |
| 수동 적합 처리/override | `main/views/review/ecm_manual_override.py`, `main/views/review/ecm_download_review_jobs.py`, `04_data_and_api.md` |
| Google Sheet -> `reference_project` 적재 | `main/management/commands/sync_reference_projects_from_sheet.py`, `04_data_and_api.md` |
| 작업 생성/취소/조회 API | `main/views/review/ecm_download_review_jobs.py` |
| worker 처리 | `main/views/review/ecm_download_review_worker.py`, `main/management/commands/run_download_worker.py` |
| 산출물 source | `main/views/review/artifact_source.py`, `06_artifact_source_ecm.md` |
| ECM HTTP 직접연동 | `main/views/review/ecm_http_client.py`, `archive/ADR/2026-07-http-ecm-source.md` |
| 점검 엔진 | `gscert_review_core.engine`, `main/views/review/ecm_download_review_inspection.py` |
| 점검규칙 기본값 | `main/management/commands/seed_download_review_rules.py` |
| 점검규칙 문서 | `02_inspection_rules.md` |
| 결과 기대값/실제값/메시지 표시 | `gscert_review_core/result_display.py` |
| 화면/프론트 | `main/templates/`, `main/static/`, `main/views/review/ecm_download_review_jobs.py` |
| Windows 로컬 앱 | `local_review_app/`, `05_windows_local_app.md`, `03_developer_guide.md` |
| LLM 점검 후보 | `main/views/review/ecm_llm_review.py`, `archive/2026-07-doc-cleanup/17_llm_review_interface.md` |

## 점검규칙을 추가하거나 바꿀 때

JSON 조건만 바꾸는 경우:

1. `02_inspection_rules.md`에서 JSON 키와 가능한 범위를 확인한다.
2. `seed_download_review_rules.py`의 실제 규칙 정의를 수정한다.
3. `seed_download_review_rules --only-real --enable --update-existing --dry-run`으로 변경을 확인한다.
4. dry-run 결과가 맞으면 `--enable --update-existing`으로 반영한다.
5. `main.tests`에 샘플 케이스를 추가하거나 기존 케이스를 보강한다.
6. 실제 zip 또는 테스트 zip으로 결과를 확인한다.

새 검사 방식이 필요한 경우:

1. `gscert_review_core.engine`에 새 `rule_type` 또는 content check type을 추가한다.
2. 웹 어댑터와 Windows 로컬 runner가 같은 공용 엔진 경로를 쓰는지 확인한다.
3. 성공/실패 메시지와 `raw_detail_json` 증거를 함께 설계한다.
4. `02_inspection_rules.md`에 새 타입을 문서화한다.
5. 새 `rule_type`은 Windows 앱 재배포가 필요한 변경인지 확인한다.

## 결과 표시를 바꿀 때

웹과 Windows 앱의 점검 결과 표시는 `gscert_review_core/result_display.py`를 공통 API로 사용한다.

수정 원칙:

1. 기대값/실제값/메시지 문구는 가능하면 `result_display.py`에서 한 번만 수정한다.
2. 웹 API는 `display_items`를 우선 내려준다.
3. Windows 앱은 공용 표시 row를 받아 같은 번호, 같은 기대값, 같은 실제값, 같은 메시지를 보여준다.
4. 표시 문구를 바꾸면 웹과 Windows 앱에서 같은 샘플 결과가 같은 문장으로 보이는지 확인한다.

## DB 컬럼이나 모델을 추가할 때

`04_data_and_api.md`를 기준으로 어느 DB에 속하는지 먼저 정한다.

| DB | 변경 기준 |
| --- | --- |
| `reference` PostgreSQL | 공유 기준정보, 프로젝트, PL 매핑, 인증이력, 점검규칙, 재점검 후에도 유지되어야 하는 수동 판단 |
| `workflow` SQLite | 서버 로컬 작업, 프로젝트 처리 상태, 점검결과, 로그, lock, 유사 분석 작업 |
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
| 현재 상태/다음 작업 | `00_README.md` |
| 점검규칙 JSON/새 rule type | `02_inspection_rules.md` |
| 운영 명령/절차 | `01_operations.md` |
| 코드 위치/검증 절차 | `03_developer_guide.md` |
| DB 구조 | `04_data_and_api.md` |
| 완료된 변경 묶음 요약 | `archive/changelog/2026-08-download-review-changes.md` |
| 기준정보/API 사용법 | `04_data_and_api.md` |
| Windows 앱 테스트/배포 | `05_windows_local_app.md` |
| ECM source/HTTP 결정 | `06_artifact_source_ecm.md`, `archive/ADR/2026-07-http-ecm-source.md` |
| 남은 결정 사항 | `00_README.md` |

## 주의사항

- 사용자 또는 이전 작업자가 만든 변경을 되돌리지 않는다.
- `workflow.db`는 서버 로컬 실행 DB다. 커밋 대상이 아니다.
- `inspection_rule`은 공유 PostgreSQL `reference` DB에 있으므로 운영 직접 수정 전에는 백업/승인을 확인한다.
- `inspection_manual_override`도 공유 PostgreSQL `reference` DB에 둔다. 재점검 후에도 유지되어야 하는 사용자 판단이므로 `inspection_result` FK에 묶지 않는다.
- 점검규칙은 가능하면 JSON으로 표현하고, 새 동작이 필요할 때만 검사 엔진 코드를 늘린다.
- 새 문서나 readme를 추가했으면 `00_README.md`에서 찾을 수 있게 연결한다.

---

# 규칙 정의와 실행 엔진의 분리 구조

웹 자동 점검과 Windows 로컬 점검 앱은 같은 규칙 정의와 같은 실행 엔진을 공유한다. 어디를 바꾸면 무엇을 다시 배포해야 하는지는 이 구조에서 결정된다.

| 구분 | 위치 | 역할 |
| --- | --- | --- |
| 규칙 정의 | `DownloadReviewRule` 모델 / `inspection_rule` 테이블(reference DB) | 어떤 규칙을 어떤 설정으로 실행할지 저장 |
| 규칙 실행 코드 | `gscert_review_core.engine` | `rule_type`별 실제 파일/문서 검사 수행 |
| 규칙 초기값/갱신 | `main/management/commands/seed_download_review_rules.py` | 코드에 정의된 기본 규칙을 DB에 seed |
| 규칙 결과 | `DownloadReviewRuleResult` / `inspection_result`(workflow DB) | 규칙별 통과/부적합/오류 결과 저장 |
| 웹 실행 흐름 | `main/views/review/ecm_download_review_worker.py` | 다운로드 후 웹 어댑터 `run_download_inspection()`으로 공용 엔진 호출 |
| Windows 앱 | `local_review_app/` | 폴더 선택, 기준정보 조회, 파일 스캔, 규칙 캐시, 공용 엔진 기반 로컬 점검 |

즉 `config_json`은 규칙별 상세 조건이고, `rule_type`은 어떤 검사 함수를 쓸지 결정하며, 실제 검사 코드는 공용 엔진에 있다. 완전히 "설정만으로 동작하는 규칙 엔진"은 아니다.

## 변경 유형별 배포 범위

| 변경 유형 | 예시 | 웹 반영 | Windows 앱 반영 |
| --- | --- | --- | --- |
| 규칙 설정 변경 | 파일명 키워드, 확장자, 기대값, 메시지 | 서버 DB 갱신 후 자동 적용 | 앱이 규칙을 다시 받으면 적용 |
| 규칙 활성/비활성 | 특정 규칙 `enabled` 변경 | 서버 DB 갱신 후 자동 적용 | 앱이 규칙을 다시 받으면 적용 |
| 기존 `rule_type`으로 표현 가능한 규칙 추가 | `required_artifact_file` 규칙 추가 | 서버 DB 갱신 후 자동 적용 | 해당 `rule_type`을 지원하면 규칙 업데이트만으로 적용 |
| 새 검사 로직 추가 | 새 `rule_type`, 새 문서 파서 | 서버 코드 배포 필요 | 앱 업데이트 필요 |
| 파서/추출 로직 수정 | Word/PDF/Excel 추출 방식 변경 | 서버 코드 배포 필요 | 앱 업데이트 필요 |
| UI 변경 | 앱 화면 구성 | - | 앱 업데이트 필요 |

공용 엔진에 아직 없는 새 `rule_type`이 추가되면 Windows 앱은 그 규칙을 `미지원`으로 표시한다. 규칙 bundle에는 `engine_min_version`이 있고, 앱은 이 값이 자신의 엔진 버전보다 높으면 실행하지 않고 업데이트를 안내한다. 현재 공용 엔진 버전과 `engine_min_version`은 모두 `0.2.0`이다.

## 규칙 배포 API

| 목적 | API |
| --- | --- |
| 규칙 버전 확인 | `GET /api/local-review/rules/manifest/` |
| 규칙 bundle 다운로드 | `GET /api/local-review/rules/bundle/` |
| 특정 버전 다운로드 | `GET /api/local-review/rules/bundle/?version=2026.06.19.1` |

manifest 응답에는 `rulebase_version`, `engine_min_version`, `checksum`, `published_at`이 들어가고, bundle 응답에는 활성 규칙만 `code`/`name`/`rule_type`/`config_json`/`severity`/`sort_order`/`enabled` 형태로 들어간다.

Windows 앱 동작 순서는 다음과 같다.

1. 앱 시작 또는 `규칙 버전 확인` 시 manifest를 호출한다.
2. 로컬 캐시의 `rulebase_version`과 서버 버전을 비교한다.
3. 서버 버전이 높으면 bundle을 내려받아 로컬 JSON 캐시에 저장한다. 기본 캐시 위치는 `%LOCALAPPDATA%\GSCertLocalReview\rules_bundle.json`이다.
4. `engine_min_version`이 앱 엔진 버전보다 높으면 프로그램 업데이트 필요를 표시한다.
5. 서버 연결에 실패하면 마지막으로 받은 캐시로 실행하고, 캐시도 없으면 점검을 막고 서버 연결을 안내한다.

## 공용 엔진의 경계

- 공용 엔진(`gscert_review_core.engine.evaluate_rules`)은 프로젝트 기준정보, 로컬 파일 목록, 규칙 목록을 입력으로 받고 규칙별 결과 객체만 반환한다. DB에 직접 저장하지 않는다.
- 웹은 반환된 결과를 `inspection_result`에 저장하고 산출물 캡처 이미지까지 보관한다.
- Windows 앱은 같은 결과를 화면에만 표시한다. 서버 DB 저장과 캡처 저장은 하지 않는다.
- 따라서 새 검사 유형을 추가할 때도 엔진에는 DB 접근 코드를 넣지 않는다. 웹 전용 저장 로직은 `ecm_download_review_inspection.py` 어댑터에 둔다.
