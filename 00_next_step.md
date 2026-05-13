# Download Review 다음 작업 인수인계

이 문서는 누적 이력 보관용이 아니라, 다른 PC나 다른 대화에서 바로 이어서 작업하기 위한 짧은 인수인계 문서다. 지난 설계와 구현 이력은 관련 설계 문서에 나누어 기록한다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 작성일: 2026-05-14
- 직전 기준 커밋: `ade28cc fix: avoid repeated sqlite data commits`
- 로컬 URL: `http://127.0.0.1:8000/download-review/`
- 테스트 편의를 위해 현재 download-review 시작 가능 시간은 `00:00-24:00`으로 열려 있다.

관련 상세 문서:

- 데이터/파일 정책: `main/data/README.md`, `11_readme_policy.md`
- DB/worker 설계: `02_database_design.md`, `09_worker_process_design.md`
- UI/API 설계: `08_ui_api_design.md`, `13_ui_mockup_design.md`
- 운영 스크립트: `10_operations_scripts.md`
- 확정/미확정 사항: `15_open_decisions.md`, `16_download_review_backend_decisions.md`

## 직전 작업

`reference.csv` 기준 흐름을 실제 운영 흐름에 맞게 `reference.xlsx -> reference.db` 흐름으로 정리했다.

- `main/data/reference.xlsx`를 Git 포함 기준 원본으로 추가했다.
- `main/data/reference.db`는 `reference.xlsx`에서 재생성되는 Git 포함 기준 DB로 유지한다.
- 더 이상 쓰지 않는 `main/data/reference.csv`, `main/data/csv`, `main/utils/build_reference_db.py`는 제거했다.
- `main/management/commands/sqlite.py` 기본 입력/출력을 `main/data/reference.xlsx`, `main/data/reference.db`로 맞췄다.
- `manage.py sqlite` 실행 후 기준 데이터 변경이 있으면 `reference.xlsx`와 `reference.db`만 `git add/commit/push`한다.
- 자동 커밋 메시지 기본값은 `data: update reference database`다.
- `--no-git-sync`를 붙이면 기존처럼 DB 생성만 하고 Git 반영은 하지 않는다.
- SQLite 내용이 논리적으로 같으면 DB 파일을 교체하지 않아 반복 실행 때 불필요한 데이터 커밋이 생기지 않게 했다.

주의: 별도 스케줄러는 추가하지 않았다. 위 Git 반영은 `manage.py sqlite` 명령을 수동으로 실행하거나 기존 `weekly.py`/배치 흐름에서 해당 명령을 호출할 때만 동작한다.

## 검증 완료

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe -m unittest discover playwright_job/tests
.\.venv\Scripts\python.exe manage.py sqlite --no-git-sync --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py sqlite --settings=myproject.ui_mock_settings
```

결과:

- Django system check 통과
- `main.tests` 22개 통과
- `playwright_job/tests` 10개 통과
- `manage.py sqlite --no-git-sync` 변경 없음 정상
- `manage.py sqlite` 기준 데이터 변경 없음 정상

## 바로 다음 작업

1. 운영 서버의 기존 `weekly.py`/배치 실행 흐름 확인
   - 현재 코드는 별도 스케줄을 만들지 않았으므로 기존 운영 방식은 유지된다.
   - 다만 기존 배치가 `manage.py sqlite`를 호출하면 이제 기준 데이터 변경 시 Git push까지 수행한다.
   - 운영에서 Git push까지 자동 수행할지, DB 생성만 할지 결정해야 한다.

2. 실제 ECM live 다운로드 검증
   - 테스트 프로젝트는 `TTA-26-00200`으로 진행한다.
   - visible 모드로 실행해 ECM 폴더 탐색, agent 폴더 선택, 전송현황, 시스템 알림, 다운로드 산출물을 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --once --live --no-headless --settings=myproject.ui_mock_settings
```

3. 다운로드 산출물 기반 점검 규칙 설계
   - 실제 파일 목록과 포맷을 확인한 뒤 30개 내외 점검 규칙을 정의한다.
   - 규칙 결과를 `ecmlist.db`의 점검 컬럼에 어떻게 매핑할지 확정한다.

4. 테스트 완료 후 시간 제한 복구
   - 현재는 테스트 때문에 모든 시간대 실행 가능 상태다.
   - 운영 전에는 시작 가능 시간을 `20:00-07:00`으로 되돌린다.

## 결정 필요

1. `manage.py sqlite`의 Git push 기본값
   - 추천: 지금처럼 기본은 Git push 수행, 로컬 검증 때만 `--no-git-sync` 사용.
   - 이유: 운영에서 `reference.xlsx`와 `reference.db`가 항상 같이 버전 관리되어 다른 PC에서 이어받기 쉽다.

2. 운영 배치에서 쓸 명령
   - 추천: 실제 운영 배치에는 `.\.venv\Scripts\python.exe manage.py sqlite`를 사용한다.
   - 이유: `weekly.py`가 `reference.xlsx`를 갱신한 뒤 DB와 Git 원격까지 한 번에 동기화할 수 있다.

3. 실제 ECM 테스트 시점
   - 추천: 다음 단계에서 `TTA-26-00200` 1건으로 visible live 테스트를 먼저 진행한다.
   - 이유: agent 팝업과 다운로드 산출물 형태는 코드만으로 확정하기 어렵고, 이후 점검 규칙 설계의 기준이 된다.
