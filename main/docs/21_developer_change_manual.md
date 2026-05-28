# Download Review 개발 변경 매뉴얼

## 목적

이 문서는 기능을 바꿀 때 어디를 수정하고 어떤 검증을 해야 하는지 빠르게 찾기 위한 개발자용 안내서다.

## 변경 유형별 수정 위치

| 변경 내용 | 우선 확인 파일 |
| --- | --- |
| 프로젝트 목록 조회, 검색, WD 표시 | `main/views/review/ecm_reference_db.py`, `main/views/review/ecm_download_review_jobs.py` |
| Google Sheet 동기화 | `main/utils/ecmList/sync_sheets.py`, `main/utils/ecmList/readme.md` |
| 작업 생성/취소/조회 API | `main/views/review/ecm_download_review_jobs.py` |
| worker 처리 | `main/views/review/ecm_download_review_worker.py`, `main/management/commands/run_download_worker.py` |
| 산출물 파일/zip 검증 | `main/views/review/ecm_download_review_inspection.py` |
| 점검규칙 기본값 | `main/management/commands/seed_download_review_rules.py` |
| 점검규칙 JSON 설명 | `main/docs/19_inspection_rule_manual.md` |
| ECM 웹 페이지 탐색 | `main/views/review/ecm_download.py`, `main/docs/03_webpage1_automation.md` |
| agent 팝업/폴더 선택 | `main/views/review/ecm_agent_popup.py`, `main/docs/04_agent_download.md` |
| 화면/프론트 | `main/templates/`, `main/static/`, `main/docs/08_ui_api_design.md` |
| DB 모델 | `main/models.py`, `main/db_routers.py`, `main/docs/02_database_design.md` |
| LLM 점검 | `main/views/review/ecm_llm_review.py`, `main/docs/17_llm_review_interface.md` |

## 점검규칙을 추가하거나 바꿀 때

JSON 조건만 바꾸는 경우:

1. `19_inspection_rule_manual.md`에서 JSON 키와 가능한 범위를 확인한다.
2. `seed_download_review_rules.py`의 `_actual_rule_spec()`을 수정한다.
3. `seed_download_review_rules --only-real --dry-run`으로 변경을 확인한다.
4. `--enable --update-existing`으로 로컬 `workflow.db`에 반영한다.
5. `main.tests`에 샘플 케이스를 추가하거나 기존 케이스를 보강한다.
6. `C:\test` 샘플 zip으로 실제 결과를 확인한다.

새 검사 방식이 필요한 경우:

1. `ecm_download_review_inspection.py`에 새 `rule_type` 또는 content check type을 추가한다.
2. JSON 키를 최소화하고 기존 키 이름과 스타일을 맞춘다.
3. 성공/실패 메시지와 `raw_detail_json` 증거를 함께 설계한다.
4. `19_inspection_rule_manual.md`에 새 타입을 문서화한다.
5. seed, 테스트, 샘플 zip 검증을 모두 갱신한다.

## DB 컬럼을 추가할 때

기준 DB와 workflow DB를 분리해서 생각한다.

| DB | 변경 기준 |
| --- | --- |
| `ecmlist.db`, `ecmlist2.db` | 기준정보/점검결과 컬럼. 동기화 스크립트와 조회 API 모두 확인 |
| `workflow.db` | Django 모델/migration/worker 결과 저장. 로컬 DB이므로 seed와 migrate 절차 확인 |

기준 DB 컬럼을 추가할 때는 다음을 확인한다.

1. `sync_sheets.py`의 테이블 생성과 기존 테이블 보강 함수.
2. `ecm_reference_db.py`의 기준정보 allowlist와 serializer.
3. `ecm_download_review_jobs.py`의 job project snapshot serializer.
4. `02_database_design.md`, `20_download_review_operations_manual.md`.

최근 추가된 예시는 Google Sheet F열을 `WD` 컬럼으로 저장하는 변경이다.

## API나 UI를 바꿀 때

1. `08_ui_api_design.md`의 계약을 먼저 확인한다.
2. API 응답 필드가 바뀌면 테스트에서 JSON shape를 확인한다.
3. 프론트 화면 텍스트와 상태 라벨은 `ecm_download_review_jobs.py`의 serializer label과 함께 맞춘다.
4. 화면 구조가 바뀌면 `13_ui_mockup_design.md`도 갱신한다.

## worker나 자동화를 바꿀 때

1. 동시에 실행되는 작업 수와 lock 범위를 확인한다.
2. 실패/재시도/heartbeat가 기존 정책과 맞는지 `06_recovery_and_lock.md`로 확인한다.
3. ECM 또는 Windows agent를 건드리면 실제 환경에서 수동 검증한다.
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
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

Google Sheet 동기화 변경 검증:

```powershell
$env:ECMLIST_SPREADSHEET_ID="스프레드시트 ID"
.\.venv\Scripts\python.exe main\utils\ecmList\sync_sheets.py
```

## 문서 갱신 체크리스트

| 바꾼 것 | 같이 갱신할 문서 |
| --- | --- |
| 현재 상태/다음 작업 | `00_next_step.md` |
| 점검규칙 JSON | `19_inspection_rule_manual.md`, `05_zip_inspection.md` |
| 운영 명령/절차 | `20_download_review_operations_manual.md`, `10_operations_scripts.md` |
| 코드 위치/검증 절차 | `21_developer_change_manual.md` |
| DB 구조 | `02_database_design.md`, `main/data/README.md` |
| UI/API 계약 | `08_ui_api_design.md` |
| 남은 결정 사항 | `15_open_decisions.md` |

## 주의사항

- 사용자 또는 이전 작업자가 만든 변경을 되돌리지 않는다.
- `workflow.db`는 로컬 실행 DB다. 커밋 대상이 아니다.
- `ecmlist.db`, `ecmlist2.db`는 기준 데이터 변경 의도가 있을 때만 커밋한다.
- 점검규칙은 가능하면 JSON으로 표현하고, 새 동작이 필요할 때만 검사 엔진 코드를 늘린다.
- 새 문서나 readme를 추가했으면 `18_manual_index.md`에서 찾을 수 있게 연결한다.
