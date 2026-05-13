# Download Review 다음 작업 인수인계

이 문서는 누적 이력 보관용이 아니라, 다른 PC나 다른 대화에서 바로 이어서 작업하기 위한 짧은 인수인계 문서다. 지난 설계와 구현 이력은 관련 설계 문서에 나누어 기록한다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 작성일: 2026-05-14
- 최신 커밋은 `git log --oneline -1`로 확인한다.
- 로컬 URL: `http://127.0.0.1:8000/download-review/`
- 테스트 편의를 위해 현재 download-review 시작 가능 시간은 `00:00-24:00`으로 열려 있다.

관련 상세 문서:

- 데이터/파일 정책: `main/data/README.md`, `11_readme_policy.md`
- DB/worker 설계: `02_database_design.md`, `09_worker_process_design.md`
- UI/API 설계: `08_ui_api_design.md`, `13_ui_mockup_design.md`
- 운영 스크립트: `10_operations_scripts.md`
- 확정/미확정 사항: `15_open_decisions.md`, `16_download_review_backend_decisions.md`

## 직전 작업

`weekly.py`의 기준 데이터 적재 흐름을 저장소 안에서 완결되도록 정리했다.

- `main/utils/weekly.py`가 더 이상 외부 `C:\Users\Administrator\Desktop\db.bat`에 의존하지 않는다.
- ECM 원천 xlsx를 내려받아 `reference.xlsx`에 append한 뒤 `manage.py sqlite`를 직접 실행한다.
- `manage.py sqlite` 기본 실행은 `reference.xlsx`와 `reference.db` 변경분을 Git commit/push한다.
- `GSCERT_SQLITE_NO_GIT_SYNC=1`을 설정하면 weekly 흐름에서도 DB 생성만 하고 Git 반영은 생략한다.
- `reference.xlsx`와 `edm_storage_state.json` 기본 경로를 저장소 기준 `main/data/`로 맞췄다.
- `인증획득제품리스트` 시트가 있으면 해당 시트를 우선 사용하고, 없으면 기존처럼 active sheet를 사용한다.
- 기존 `exit.bat`, `run.bat` 보조 실행 흐름은 유지했다.
- 새 스케줄러는 추가하지 않았다. 기존 Windows 작업 스케줄러나 운영 배치가 `weekly.py`를 실행할 때만 동작한다.

주요 환경변수:

```text
GSCERT_REFERENCE_XLSX
GSCERT_WEEKLY_DOWNLOAD_DIR
GSCERT_EDM_STORAGE_STATE
GSCERT_PYTHON
GSCERT_MANAGE_PY
GSCERT_DJANGO_SETTINGS
GSCERT_SQLITE_NO_GIT_SYNC
```

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\utils\weekly.py
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe -m unittest discover playwright_job/tests
.\.venv\Scripts\python.exe manage.py sqlite --no-git-sync --settings=myproject.ui_mock_settings
```

결과:

- `weekly.py` compile 통과
- Django system check 통과
- `main.tests` 22개 통과
- `playwright_job/tests` 10개 통과
- `manage.py sqlite --no-git-sync` 변경 없음 정상

## 바로 다음 작업

1. 실제 ECM live 다운로드 검증
   - 테스트 프로젝트는 `TTA-26-00200`으로 진행한다.
   - visible 모드로 실행해 ECM 폴더 탐색, agent 폴더 선택, 전송현황, 시스템 알림, 다운로드 산출물을 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --once --live --no-headless --settings=myproject.ui_mock_settings
```

2. 다운로드 산출물 기반 점검 규칙 설계
   - 실제 파일 목록과 포맷을 확인한 뒤 30개 내외 점검 규칙을 정의한다.
   - 규칙 결과를 `ecmlist.db`의 점검 컬럼에 어떻게 매핑할지 확정한다.

3. 테스트 완료 후 시간 제한 복구
   - 현재는 테스트 때문에 모든 시간대 실행 가능 상태다.
   - 운영 전에는 시작 가능 시간을 `20:00-07:00`으로 되돌린다.

## 결정 필요

1. weekly 운영 시 Git push 기본값
   - 추천: 기본 Git push 유지, 운영자가 로컬 검증만 할 때 `GSCERT_SQLITE_NO_GIT_SYNC=1` 사용.
   - 이유: `reference.xlsx`와 `reference.db`가 원격 저장소에 함께 올라가야 다른 PC와 서버의 기준 데이터가 맞는다.

2. 실제 ECM 테스트 시점
   - 추천: 다음 단계에서 `TTA-26-00200` 1건으로 visible live 테스트를 먼저 진행한다.
   - 이유: agent 팝업과 다운로드 산출물 형태는 코드만으로 확정하기 어렵고, 이후 점검 규칙 설계의 기준이 된다.
