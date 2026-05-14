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

## 직전 작업

센터 선택 기능을 추가했다.

- UI 프로젝트 선택 탭에 센터 선택(`상암`, `영남`)을 추가했다.
- 상암 선택 시 `main/data/ecmlist.db`를 조회/갱신한다.
- 영남 선택 시 `main/data/ecmlist2.db`를 조회/갱신한다.
- `ecmlist2.db`는 테스트를 위해 `ecmlist.db`와 같은 구조로 생성했다.
- 작업 요청 payload에 `center`를 포함한다.
- `automation_job`, `automation_job_project`에 `center_code`를 추가했다.
- 같은 프로젝트번호가 두 센터 DB에 모두 있어도 선택한 센터 기준으로 중복 검사와 write-back을 처리한다.
- ECM 자동화는 센터에 따라 루트 폴더를 바꾼다.
  - 상암: `상암AX센터`
  - 영남: `영남AX센터`
- 기존 상암 루트 중복 대응은 `ECM_TREE_ROOT_INDEX=1`로 유지한다.
- 영남 루트 기본 index는 `ECM_TREE_ROOT_INDEX_YEONGNAM=0`이다.
- 로컬 `workflow.db`에 `main.0002_downloadreview_center_code` migration을 적용했다.

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_download_review_centers.py main\views\review\ecm_reference_db.py main\views\review\ecm_download_review_jobs.py main\views\review\ecm_download.py main\views\review\ecm_download_review_worker.py
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py migrate --database=workflow --settings=myproject.ui_mock_settings
```

## 바로 다음 작업

1. UI에서 영남 선택 후 프로젝트 목록과 작업 요청 흐름을 브라우저로 확인한다.
2. 영남 live 다운로드를 실제 프로젝트 1건으로 검증한다.
   - ECM 트리가 `영남AX센터 > {연도}년 시험서비스 > 01 GS인증시험(1등급) > 프로젝트폴더` 순서로 열리는지 확인한다.
   - 필요하면 `ECM_TREE_ROOT_INDEX_YEONGNAM` 값을 조정한다.
3. 실제 규칙 등록 방식을 정하고 `inspection_rule` seed 관리 명령을 추가한다.
4. 테스트가 끝나면 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 결정 필요

1. 영남 ECM 트리에 `영남AX센터`가 여러 개 보이는지 확인한다.
   - 추천: 먼저 기본값 `ECM_TREE_ROOT_INDEX_YEONGNAM=0`으로 테스트한다.
   - 이유: 상암은 같은 이름이 2개라 두 번째를 쓰도록 조정했지만, 영남은 아직 중복 여부를 확인하지 않았기 때문이다.
