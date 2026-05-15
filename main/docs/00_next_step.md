# Download Review Next Step

이 문서는 전체 이력 보관용이 아니라 다른 PC에서 바로 이어가기 위한 직전 작업 인수인계 문서다.
상세 설계와 누적 이력은 `main/docs/`의 번호 문서와 각 폴더의 `readme.md`에 나누어 기록한다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 로컬 URL: `http://127.0.0.1:8000/download-review/`
- 서버: `manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings`
- 테스트용 시작 가능 시간: 현재 `00:00-24:00`
- 운영 원복 마커: `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`
- 운영 기준 시간: `20:00-07:00`
- 숫자 prefix 설계 문서는 최상위 루트가 아니라 `main/docs/`에서 관리한다.

## 직전 작업

센터 선택과 점검 규칙 seed 준비를 정리했다.

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
- 영남은 `상암AX센터` 바로 아래 같은 수준에 있는 `영남AX센터` 1개로 확인되어 `ECM_TREE_ROOT_INDEX_YEONGNAM=0`을 기본값으로 확정했다.
- 로컬 `workflow.db`에 `main.0002_downloadreview_center_code` migration을 적용했다.
- `main/services` 폴더는 더 이상 참조되지 않아 삭제했다.
- `seed_download_review_rules` 관리 명령을 추가했다.
  - 기본 실행은 산출물 컬럼 기준 draft 규칙을 비활성 상태로 생성한다.
  - `--enable`을 명시해야 활성화한다.
  - `--update-existing`을 명시해야 기존 규칙의 이름/config/order를 갱신한다.
- 로컬 `workflow.db`에는 비활성 draft 규칙 18개를 생성했다.
- draft 규칙은 실제 규칙이 없는 동안 테스트용으로 남겨둔다.
- 실제 규칙이 만들어지면 매핑되는 draft 규칙을 삭제하고 실제 규칙으로 테스트한다.
- UI의 센터 선택을 프로젝트 선택 탭 내부 select에서 상단 상태 바 안의 작은 탭(`상암`, `영남`)으로 변경했다.
- 센터 탭 변경 시 프로젝트 선택과 작업 조회는 선택한 센터 기준으로 다시 조회된다.
- worker와 현재 작업 진행 상황은 센터와 무관한 전체 서버 기준으로 표시한다.
- `GET /api/jobs/`는 `center=sangam|yeongnam` 필터를 지원한다.
- 로컬 Codex skill `gscert-download-review-maintainer`를 생성했다.
  - 위치: `C:\Users\jh910\.codex\skills\gscert-download-review-maintainer`
  - 용도: download-review UI/API/worker/DB/문서 handoff 유지보수

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_download_review_centers.py main\views\review\ecm_reference_db.py main\views\review\ecm_download_review_jobs.py main\views\review\ecm_download.py main\views\review\ecm_download_review_worker.py main\management\commands\seed_download_review_rules.py
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py migrate --database=workflow --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --dry-run --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe C:\Users\jh910\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\jh910\.codex\skills\gscert-download-review-maintainer
```

브라우저에서 `/download-review/`를 새로고침한 뒤 상단 센터 탭 노출과 영남 탭 전환을 확인했다.

## 바로 다음 작업

1. 영남 live 다운로드를 실제 프로젝트 1건으로 검증한다.
   - ECM 트리가 `영남AX센터 > {연도}년 시험서비스 > 01 GS인증시험(1등급) > 프로젝트폴더` 순서로 열리는지 확인한다.
2. 다른 PC에서도 skill을 쓰려면 `gscert-download-review-maintainer` 폴더를 해당 PC의 `.codex\skills`로 복사한다.
3. 실제 산출물 파일명 기준을 확인한 뒤 `seed_download_review_rules --enable --update-existing` 적용 여부를 결정한다.
4. 파일 존재/확장자/파일명 포함 규칙부터 실제 산출물 컬럼과 1:1 매핑한다.
5. 테스트가 끝나면 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 결정 필요

1. draft 규칙을 언제 삭제할지 결정해야 한다.
   - 추천: 매핑되는 실제 규칙이 만들어진 시점에 해당 draft 규칙만 삭제한다.
   - 이유: 실제 규칙이 없는 동안에는 테스트용 기준이 필요하고, 실제 규칙과 draft 규칙이 동시에 활성화되면 중복 판정이 생길 수 있다.
2. 영남 live 테스트 프로젝트를 선택해야 한다.
   - 추천: 사용자가 지정한 `TTA-26-00200`으로 먼저 진행한다.
   - 이유: 이미 테스트 후보로 공유된 번호라 재확인 비용이 적고, 센터 분기 동작을 빠르게 확인할 수 있다.
