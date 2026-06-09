# GSCert Next Step

이 문서는 전체 이력 보관용이 아니라, 다른 PC나 다음 작업자가 바로 이어가기 위한 최신 인수인계 문서다. 자세한 목차는 `18_manual_index.md`를 먼저 본다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 보안 페이지 URL: `http://127.0.0.1:8000/security/`
- 다운로드 검토 페이지 URL: `http://127.0.0.1:8000/download-review/`
- 서버 실행 예시: `.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- 다운로드 검토 테스트용 시작 가능 시간: 현재 `00:00-24:00`
- 운영 기준 시간: `20:00-07:00`
- 운영 복원 마커: `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`

## 다른 개발 PC에서 시작

새로 저장소를 받는 경우:

```powershell
git clone https://github.com/TTAJihoon/GSCert.git
cd GSCert
git switch codex-job-runner-persistence
git pull
```

이미 저장소가 있는 경우:

```powershell
git switch codex-job-runner-persistence
git pull
```

Codex skill을 설치하는 경우:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force `
  ".\main\docs\codex_skills\gscert-download-review-maintainer" `
  "$env:USERPROFILE\.codex\skills\gscert-download-review-maintainer"
```

## 먼저 읽을 문서

1. `main/docs/18_manual_index.md`
2. `main/docs/20_download_review_operations_manual.md`
3. 점검규칙을 수정한다면 `main/docs/19_inspection_rule_manual.md`
4. 코드를 수정한다면 `main/docs/21_developer_change_manual.md`
5. 남은 결정 사항은 `main/docs/15_open_decisions.md`

## 최근 완료 작업

요청 로그 템플릿을 추가했다.

- `main.request_logging.RequestLogMiddleware`를 추가해 Django 요청 종료 시점에 구조화 로그를 남긴다.
- 성공/일반 응답은 `ACCESS | 2026-.. KST | request_id=... | ip=... | method=... | path=... | status=... | duration_ms=...` 형식이다.
- 500 이상 응답이나 예외는 `ERROR | ... | error=... | message=...` 형식으로 남긴다.
- `X-Forwarded-For`, `X-Real-IP`, `REMOTE_ADDR` 순서로 IP를 확인한다.
- `/history/` POST 로그에는 검색 조건과 결과 수를 포함한다.
- `/summarize_document/` POST 로그에는 파일/수동 입력 모드, 수동 입력 문장, LLM 요약/검색 문장, 결과 수를 포함한다.
- `/generate_prdinfo/` POST 로그에는 업로드 파일명, 시험신청번호, AI 추천 SW 분류/키워드를 포함한다.
- 기존 `print`로 찍히던 Gemini/Gemma 단계 출력은 기본 로그에 섞이지 않도록 `logger.debug`로 낮췄다.

`weekly.py` 기준 데이터 갱신 실행 방식을 보강했다.

- `.\.venv\Scripts\python.exe main\utils\weekly.py 20260608`처럼 첫 번째 인자로 대상 날짜를 넘기면 이 값이 `GSCERT_WEEKLY_TARGET_DATE`보다 우선한다.
- 입력 날짜는 ECM 문서명 `인증획득제품(YYYYMMDD)` 선택에 사용된다.
- ECM 연도 폴더도 현재 연도가 아니라 입력 날짜의 연도 기준으로 선택한다.
- 현재 기준 데이터 흐름은 `reference.xlsx` 갱신 후 `manage.py sqlite`로 `reference.db`를 재생성하는 방식이다. `reference.csv`가 갱신된다면 최신 `codex-job-runner-persistence`의 `weekly.py`가 아닌 오래된 파일을 실행 중인지 확인한다.
- `weekly.py`가 `manage.py sqlite --force`를 실행할 때 프로젝트/상위 폴더의 `.venv` 또는 `venv` Python을 자동 탐색한다.
- `reference.xlsx`와 `reference.db` 경로를 `manage.py sqlite`에 명시적으로 전달한다.
- `main/data/weekly_gs_sync.log`에 DB 적재 stdout/stderr와 최종 `reference.db` 파일 크기/수정시각을 남긴다.
- weekly 흐름은 `ECM 다운로드 -> reference.xlsx 업데이트 -> reference.db 업데이트`만 수행한다.
- 서버 종료/시작용 `exit.bat`/`run.bat`는 weekly에서 더 이상 호출하지 않는다.
- `manage.py sqlite` 출력은 Windows 코드페이지 영향을 피하기 위해 ASCII 문구로 정리했다.
- `weekly.py`가 `manage.py sqlite`를 호출할 때 `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`을 넘긴다.
- `history.html` 시험 이력 조회 테이블에 `SW분류` 열을 추가하고, 제품 개요 열을 80px 줄였다.
- 시험 이력 검색 조건에 `SW분류`, `시험원`, 전체 입력값 지우기 버튼을 추가했다.
- `xlsx_to_sqlite.py`는 `S/W분류`를 `SW분류`로 정규화하고, 원천 컬럼 변형이 있어도 `SW분류` 컬럼을 보장한다.

`WD` 기준 컬럼 반영과 산출물 점검 규칙 1~5번 실제 구현이 완료됐다.

- `sync_sheets.py`가 Google Sheet F열 값을 `WD` 컬럼으로 저장한다.
- `main/data/ecmlist.db`, `main/data/ecmlist2.db`에 `WD` 컬럼이 추가됐다.
- 프로젝트 조회 API와 작업 snapshot 응답에서 `wd` 값을 포함한다.
- 실제 규칙 seed 명령에 `--only-real` 옵션이 추가됐다.
- 1번 계약서, 3번 수수료산정표, 4번 시험환경구성도는 `required_artifact_file` 규칙 타입으로 구현됐다.
- 2번 합의서(PDF), 5번 품질특성별제품정보기재사항은 `document_artifact_check` 규칙 타입으로 구현됐다.
- zip 내부 파일 경로까지 검사할 수 있다.
- 각 규칙의 폴더 탐색, 파일명 키워드, 확장자, 개수, 문서 내용 검사 조건은 `inspection_rule.config_json`에 저장한다.

문서 정리도 진행했다.

- `18_manual_index.md`: 전체 문서 목차와 사용 가이드
- `19_inspection_rule_manual.md`: 점검규칙 JSON 설명과 수정 절차
- `20_download_review_operations_manual.md`: 운영/검증 매뉴얼
- `21_developer_change_manual.md`: 개발 변경 위치와 검증 체크리스트

프로젝트 목록 API 안정화도 반영했다.

- 기준 DB 조회는 정상인데 `workflow.db`의 활성 작업 상태 조회가 실패하는 경우, 프로젝트 목록 전체를 실패시키지 않고 활성 작업 상태만 빈 값으로 표시한다.
- 이 경우에도 완료 프로젝트는 기존 `점검결과` 기준으로 `완료` 상태를 유지한다.

## 현재 실제 구현된 규칙

| 번호 | 산출물 | 구현 상태 |
| --- | --- | --- |
| 1 | 계약서 | 완료 |
| 2 | 합의서(PDF) | 완료 |
| 3 | 수수료산정표 | 완료 |
| 4 | 시험환경구성도 | 완료 |
| 5 | 품질특성별제품정보기재사항 | 완료 |
| 6 | 기능리스트 | 다음 구현 대상 |
| 7 | 시험계획서(PDF) | 다음 구현 대상 |

## 검증 완료

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
git diff --check
```

`C:\test` 샘플 zip과 프로젝트 번호 `TTA-26-00266` 기준으로 1~5번 규칙은 모두 `O`로 확인됐다.

프로젝트 목록 핫픽스 후 추가 검증:

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py test main.tests.DownloadReviewProjectsApiTests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
```

전체 테스트는 35개 통과했다.

요청 로그 템플릿 반영 후 추가 검증:

```powershell
python -m py_compile main\request_logging.py main\views\testing\history.py main\views\testing\similar_summary.py main\views\testing\similar_GPT.py main\views\certy\prdinfo_GPT.py main\views\certy\prdinfo_generate.py myproject\settings.py myproject\ui_mock_settings.py
node --check main\static\scripts\testing\security_GPT_popup.js
node --check main\static\scripts\testing\security_editable.js
```

현재 작업 워크트리에는 Django 실행용 `.venv`가 없어 `manage.py check`는 실행하지 못했다.

`weekly.py` 날짜 인자 보강 후 추가 검증:

```powershell
python -m py_compile main\utils\weekly.py
```

`weekly.py` DB 적재 로그 보강 후 추가 검증:

```powershell
python -m py_compile main\utils\weekly.py
```

## 바로 다음 작업

1. 6번 기능리스트 구현 전에 `.xls` 샘플 처리 의존성을 결정한다.
   - 실제 `.xls`가 계속 들어오면 `xlrd` 계열 reader 의존성을 추가한다.
2. 6번 기능리스트와 7번 시험계획서(PDF)를 실제 코드로 구현한다.
   - Excel 구버전 처리, Word 표 위치/일정 값 검사를 포함하면 1~7번 기본 묶음이 완성된다.
3. `WD` 값이 실제 Google Sheet F열에서 운영 DB로 들어오는지 다음 동기화 때 한 번 더 확인한다.
4. 8~18번 산출물 점검 규칙을 같은 형식으로 정의한다.
   - 한 번에 3~5개씩 정의하는 것이 좋다.
5. 테스트가 끝나면 download-review 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`
6. 운영 서버에 반영한 뒤 `uvicorn_*_out.log`에서 새 `ACCESS`/`ERROR` 한 줄 로그가 시간, IP, 검색어/요약 문장을 포함하는지 확인한다.

## 변경 파일 요약

최근 작업으로 변경된 주요 파일은 다음과 같다.

- `main/docs/00_next_step.md`
- `main/request_logging.py`
- `myproject/settings.py`
- `myproject/ui_mock_settings.py`
- `main/views/testing/history.py`
- `main/views/testing/similar_summary.py`
- `main/views/testing/similar_GPT.py`
- `main/views/certy/prdinfo_GPT.py`
- `main/views/certy/prdinfo_generate.py`
- `main/docs/02_database_design.md`
- `main/docs/05_zip_inspection.md`
- `main/docs/08_ui_api_design.md`
- `main/docs/15_open_decisions.md`
- `main/docs/18_manual_index.md`
- `main/docs/19_inspection_rule_manual.md`
- `main/docs/20_download_review_operations_manual.md`
- `main/docs/21_developer_change_manual.md`
- `main/docs/codex_skills/gscert-download-review-maintainer/references/rules.md`
- `main/data/README.md`
- `main/utils/ecmList/readme.md`
- `main/management/commands/seed_download_review_rules.py`
- `main/tests.py`
- `main/utils/ecmList/sync_sheets.py`
- `main/views/review/ecm_download_review_inspection.py`
- `main/views/review/ecm_download_review_jobs.py`
- `main/views/review/ecm_reference_db.py`
- `main/data/ecmlist.db`
- `main/data/ecmlist2.db`
