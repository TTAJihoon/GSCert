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

ECM live 다운로드 흐름을 `TTA-26-00200`으로 검증했다.

- Chrome local-network-access-check 관련 launch option을 설정값으로 추가했다.
- ECM 트리에서 두 번째 `상암AX센터`를 사용하도록 `ECM_TREE_ROOT_INDEX=1`을 적용했다.
- jstree API 기반으로 폴더 open/select를 보강했다.
- 프로젝트 폴더 클릭 후 문서 목록 3건이 표시되고 전체 선택되는 것을 확인했다.
- 다운로드 메뉴 `파일 다운로드` 클릭 후 Windows agent 팝업을 처리했다.
- 작업 표시줄에 표시되지 않는 모달 팝업까지 잡을 수 있도록 Win32 후보 탐지를 추가했다.
- 팝업 안에서 새 폴더를 만들고 생성된 TreeItem을 실제 클릭한 뒤 확인하도록 수정했다.
- live worker 결과: 성공 1건, 실패 0건
- 저장 폴더 확인: `C:\Users\jh910\Downloads\TTA-26-00200_2`
- 다운로드 파일 확인: 3개 파일
- 테스트로 변경된 `main/data/ecmlist.db`는 Git 기준 상태로 원복했다.

## 구조 정리

download-review 관련 파일은 기존 review 영역 구조에 맞춰 이동했다.

- API view: `main/views/review/ecm_download_review_api.py`
- template: `main/templates/review/ecm_download_review.html`
- CSS: `main/static/css/review/ecm_download_review.css`
- JS: `main/static/scripts/review/ecm_download_review.js`
- Python: `main/views/review/ecm_*.py`

앞으로 ECM 제출물 점검 관련 신규 파일은 아래 위치에 두고 파일명에 `ecm_` prefix를 붙인다.

- Python: `main/views/review`
- JavaScript: `main/static/scripts/review`
- CSS: `main/static/css/review`
- HTML: `main/templates/review`

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_agent_popup.py main\views\review\ecm_download_review_worker.py main\views\review\ecm_download.py
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe -m unittest discover playwright_job/tests
```

## 바로 다음 작업

1. API 계약은 `main/docs/08_ui_api_design.md` 기준으로 관리한다.
2. 다음 기능은 점검 결과 저장/표시 흐름 확정이다.
   - 작업에 포함되어 실제 점검한 프로젝트마다 규칙 개수만큼 `DownloadReviewRuleResult`를 저장한다.
   - 통과한 규칙과 실패한 규칙을 모두 저장한다.
   - 프로젝트별 최종 결과는 규칙 결과에서 파생한다.
   - 모든 규칙 통과: 프로젝트 `review_status=completed`, `ecmlist.db` 점검결과 `O`
   - 하나라도 부적합: 프로젝트 `review_status=needs_fix`, `ecmlist.db` 점검결과 `X`
   - `ecmlist.db`의 산출물별 점검 컬럼은 실제 점검규칙과 1:1로 대응하므로 그대로 사용한다.
   - 각 산출물별 점검 컬럼에는 최신 규칙 결과의 `O/X`만 기록한다.
   - 미실행/대상 없음 기본값은 빈 값으로 둔다.
   - 다운로드/agent/분석 실행 실패: workflow DB에는 보류/실패로 남기고, `ecmlist.db`의 규칙별 `O/X` 판정과 섞지 않는다.
   - 사용자 화면에는 서버 절대경로를 보여주지 않고 프로젝트 폴더 기준 파일명/상대 경로만 보여준다.
3. 분석 완료 후 cleanup 흐름을 구현한다.
   - 다운로드 폴더와 파일은 규칙 분석 완료 후 삭제한다.
   - 삭제 전 파일명, 크기, 규칙 결과, 오류 메시지는 DB에 저장한다.
   - `ecmlist.db`는 삭제 없이 프로젝트별 점검결과와 산출물 컬럼만 추가/수정한다.
4. UI 상세 팝업 표시 흐름을 정리한다.
   - 프로젝트 선택 탭의 프로젝트 행 `상세` 버튼: 해당 프로젝트의 최신 점검 결과를 표시한다.
   - 작업 조회 탭의 프로젝트 행 `상세` 버튼: 선택한 작업 요청 기준의 규칙 결과를 표시한다.
   - 실패/보류 건은 같은 팝업에서 사용자용 오류 메시지와 관리자 로그 참조용 event 정보를 표시한다.
   - 규칙 결과 API는 조회 전용으로 유지한다.
   - 규칙 결과는 worker가 생성한 실행 증거이며, 웹에서 직접 수정하지 않는다.
5. 샘플 점검규칙 구현은 최대한 뒤로 미룬다.
   - 먼저 저장 구조, 표시 방식, cleanup 흐름을 고정한다.
6. 테스트가 끝나면 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 결정 필요

1. 다음 개발을 결과 저장/표시/cleanup 흐름부터 진행할지 결정한다.
   - 추천: 진행한다.
   - 이유: 샘플 규칙을 뒤로 미뤄도 저장 구조와 UI 상세 팝업 계약은 먼저 고정할 수 있다.
