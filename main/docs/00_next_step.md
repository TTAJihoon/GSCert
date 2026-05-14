# Download Review Next Step

이 문서는 전체 이력 보관용이 아니라 다른 PC에서 바로 이어가기 위한 직전 작업 인수인계 문서다.
상세 설계와 누적 이력은 관련 설계 문서와 각 폴더의 `readme.md`에 나누어 기록한다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 로컬 URL: `http://127.0.0.1:8000/download-review/`
- 서버: `manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings`
- 테스트용 시작 가능 시간: 현재 `00:00-24:00`
- 운영 전 원복 마커: `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`
- 운영 기준 시간: `20:00-07:00`
- 숫자 prefix 설계 문서는 `main/docs/`에서 관리한다.
- 각 코드/템플릿/static 폴더의 `readme.md`는 해당 폴더 안에 유지한다.

## 직전 작업

점검 결과 저장/표시/cleanup 흐름을 코드에 반영했다.

- `main/views/review/ecm_download_review_inspection.py`를 추가했다.
- `inspection_rule`에 등록된 활성 규칙을 읽어 `inspection_result`에 통과/실패 결과를 모두 저장한다.
- 현재 지원하는 규칙 유형:
  - `min_file_count`
  - `filename_contains_project_number`
  - `required_extension`
  - `required_file_name_contains`
  - `all_files_non_empty`
- 활성 규칙이 없거나 지원하지 않는 규칙 유형이면 프로젝트를 보류/실패로 남기고 `ecmlist.db`의 O/X 판정은 갱신하지 않는다.
- live worker는 다운로드 파일 확인 후 점검규칙 검사 단계로 넘어간다.
- 점검 완료 시 프로젝트 최종 결과를 규칙 결과에서 파생한다.
  - 모든 규칙 통과: `review_status=completed`, `ecmlist.db` 점검결과 `O`
  - 하나라도 부적합: `review_status=needs_fix`, `ecmlist.db` 점검결과 `X`
- `ecmlist.db` 산출물별 점검 컬럼에는 해당 규칙의 최신 `O/X`만 기록한다.
- 다운로드/agent/분석 실행 실패는 workflow DB에 보류/실패로 남기고, `ecmlist.db`의 규칙 판정과 섞지 않는다.
- 분석 완료 또는 다운로드 후 실패 처리 시 다운로드 폴더 cleanup을 시도한다.
- cleanup은 `AGENT_DOWNLOAD_BASE_DIR` 아래에 있고 폴더명에 프로젝트번호가 포함된 디렉터리만 삭제한다.
- tracked `main/data/ecmlist.db`의 기존 한글 판정값은 `O/X` 형식으로 정규화했다.
- UI는 `O`를 `완료`, `X`를 `수정 필요`, 빈 값을 `미점검`으로 표시한다.
- 규칙 결과 API는 조회 전용이다. 규칙 결과는 worker가 생성한 실행 증거이며 웹에서 직접 수정하지 않는다.

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_download_review_inspection.py main\views\review\ecm_download_review_worker.py main\views\review\ecm_reference_db.py main\views\review\ecm_download_review_jobs.py
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
```

## 바로 다음 작업

1. 실제 점검규칙을 `inspection_rule`에 등록하는 방식을 정한다.
   - 우선은 관리 명령이나 seed 스크립트로 등록하는 방식이 적합하다.
   - 운영자가 웹에서 규칙을 수정하는 기능은 나중에 필요성이 확정되면 별도 mutation API로 설계한다.
2. 기존 `ecmlist.db` 산출물 컬럼과 실제 규칙을 1:1로 매핑한다.
   - 규칙 `code` 또는 `config_json.artifact_column`에 산출물 컬럼명을 넣으면 write-back 대상이 된다.
3. 실제 파일 내용 검사 규칙을 하나씩 추가한다.
   - 먼저 파일 존재/확장자/파일명 포함 규칙부터 붙인다.
   - Word/Excel/PDF 내부 값 검사는 이후 단계에서 추가한다.
4. UI에서 규칙 결과 상세 팝업을 다시 확인한다.
   - 프로젝트 선택 탭 `상세`: 프로젝트 최신 점검 결과
   - 작업 조회 탭 `상세`: 선택한 작업 기준 점검 결과
5. 테스트가 끝나면 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 결정 필요

1. 다음 개발에서 실제 규칙 등록 방식을 먼저 정할지 결정한다.
   - 추천: 관리 명령으로 seed하는 방식부터 진행한다.
   - 이유: 지금은 로그인/관리 UI가 없으므로 웹 수정 기능을 만들기보다, Git에 남는 코드/명령으로 규칙 목록을 재현 가능하게 만드는 편이 안전하다.
