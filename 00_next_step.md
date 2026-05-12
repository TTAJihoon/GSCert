# Download Review 다음 작업 인수인계

## 현재 기준

- 기준 브랜치: `codex-job-runner-persistence`
- 검토 대상 브랜치: `origin/feature/stages-4-9-automation`
- 검토 대상 커밋: `0dc42a2 feat: implement stages 4-9 (ops scripts, ECM automation, agent popup, download verify)`
- 기준 커밋: `7e275e7 Connect download review result tab to API`
- 작성일: 2026-05-12

`codex-job-runner-persistence` 브랜치는 현재 UI 목업, 프로젝트 목록 API, 작업 요청/대기/예약 API, dry-run worker, `ecmlist.db` write-back, 결과 조회 API까지 반영되어 있다.

`feature/stages-4-9-automation` 브랜치는 다음 단계 구현 초안을 추가했다.

- Stage 4: 서버/worker 시작, 중지, 상태 조회 PowerShell 운영 스크립트
- Stage 5: ECM 화면 Playwright 자동화 골격
- Stage 6-8: Windows agent 폴더 선택, 전송상황, 중복 알림 처리 골격
- Stage 9: 다운로드 파일 검증 골격

## 2026-05-12 병합 반영 메모

현재 브랜치(`codex-backend-foundation`)에는 `origin/codex-job-runner-persistence`와
`origin/feature/stages-4-9-automation`의 변경을 순서대로 병합했다.

병합하면서 아래 항목은 코드에 반영했다.

- Playwright import를 live worker 실행 시점으로 늦춰 UI/API/dry-run 테스트가 자동화 의존성 없이 import될 수 있게 했다.
- `run_download_worker`와 `start_worker.ps1`의 기본 실행을 dry-run으로 바꾸고, 실제 자동화는 `--live`/`-Live`를 명시해야 실행되게 했다.
- live worker의 ECM 다운로드와 Windows agent 팝업 구간을 `async_ecm_agent_lock()`으로 감쌌다.
- live 실패 시 프로젝트 `review_status`를 `held`로 저장하고 `ecmlist.db`에는 `점검결과=보류` write-back을 시도하게 했다.
- 다운로드 성공만으로 `완료`를 쓰지 않고 `downloaded`/`unreviewed` 상태로 남기게 했다.
- 0 byte 다운로드 파일은 실패로 처리하고, 프로젝트 번호 미포함 파일은 경고로만 기록하게 했다.
- Django runserver 운영 스크립트 명칭과 PID 파일을 Uvicorn 표현에서 개발/검증용 runserver 표현으로 정리했다.
- Django 5.2 기준 공통 의존성과 Windows 자동화 의존성을 `requirements.txt`/`requirements-automation.txt`로 분리했다.

남은 실제 확인 항목은 ECM/Windows agent가 있는 PC에서 `-Live -NoHeadless`로 visible 테스트를 실행해 팝업 발생 순서와 실제 다운로드 산출물 형태(zip 단일 파일인지 개별 파일인지)를 확인하는 것이다.

## 2026-05-13 로컬 동기화 및 실행 준비

다른 PC에서 병합된 최신 `codex-job-runner-persistence`를 로컬로 pull했다.

- pull 직후 기준 커밋: `916f1e1 merge: integrate stages 4-9 automation`
- pull 방식: fast-forward
- 문서 갱신 후 최신 HEAD는 `git log --oneline -1`로 확인한다.
- 작업트리: clean 상태에서 검증 시작
- 로컬 서버: `http://127.0.0.1:8000/download-review/`
- 서버 PID는 실행 시점마다 달라지므로 문서에 고정하지 않는다.
- 현재 수동 실행한 mock 서버는 `run/django_runserver.pid`를 만들지 않으므로 `status.ps1`에는 서버 PID가 표시되지 않을 수 있다. HTTP 200 응답으로 별도 확인했다.

로컬 자동화 실행 준비:

- `requirements-automation.txt` 설치 완료
- Playwright Chromium 설치 완료
- `playwright`, `pywinauto`, `win32gui` import 확인 완료
- Playwright headless Chromium smoke test 완료
- live automation import 확인 완료

실행한 검증:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe -m unittest discover playwright_job/tests
.\.venv\Scripts\python.exe manage.py run_download_worker --once --dry-run --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py run_download_worker --once --live --no-headless --settings=myproject.ui_mock_settings
powershell -ExecutionPolicy Bypass -File .\status.ps1
```

결과:

- Django system check: 통과
- `main.tests`: 18개 통과
- `playwright_job/tests`: 10개 통과
- dry-run worker: 시작 가능한 작업 없음으로 idle 정상 종료
- live worker: 시작 가능한 작업 없음으로 idle 정상 종료
- `status.ps1`: PowerShell 기본 실행 정책에서는 차단되며, `ExecutionPolicy Bypass`로 실행 시 정상 출력

현재 시간 확인:

```text
2026-05-13 08:31:07 +09:00
```

따라서 실제 ECM 다운로드 live 테스트는 시작 가능 시간인 20:00-07:00 구간에 진행해야 한다. 지금 단계에서 다음 실제 검증은 테스트 프로젝트 1건을 대기열에 넣은 뒤 아래 명령으로 visible 실행하는 것이다.

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --once --live --no-headless --settings=myproject.ui_mock_settings
```

운영 스크립트로 실행할 때는 다음 명령을 사용한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start_worker.ps1 -Live -Once -NoHeadless
```

실제 live 테스트에서 반드시 확인할 항목:

- ECM 페이지가 정상 열리는지
- 프로젝트 폴더 탐색이 실제 폴더 구조와 맞는지
- 전체 선택 체크박스와 고급 메뉴 selector가 맞는지
- Windows 폴더 찾아보기 팝업이 기본 다운로드 경로에서 시작하는지
- 새 폴더 생성 방식이 실제 팝업에서 동작하는지
- 전송현황 창과 시스템 알림 창의 발생 순서
- 다운로드 산출물이 zip 단일 파일인지 개별 파일 묶음인지
- 실패 시 `workflow.db` 상세 오류와 `ecmlist.db` `점검결과=보류` write-back이 맞는지

## 다른 PC에서 바로 이어갈 때

```powershell
git fetch origin codex-job-runner-persistence
git fetch origin feature/stages-4-9-automation
git switch codex-job-runner-persistence
git status --short --branch
Get-Content .\00_next_step.md
```

하위 브랜치 코드를 직접 확인할 때:

```powershell
git switch -c stages-4-9-automation --track origin/feature/stages-4-9-automation
git diff --stat codex-job-runner-persistence...stages-4-9-automation
git diff --name-status codex-job-runner-persistence...stages-4-9-automation
```

## 검증 결과

검토 대상 브랜치에서 다음 명령을 실행했다.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe -m py_compile main\services\ecm_download.py main\services\agent_popup.py main\services\download_verify.py main\services\download_review_worker.py main\management\commands\run_download_worker.py
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
```

결과:

- Django system check: 통과
- Python compile check: 통과
- Django test: 실패

테스트 실패 원인:

```text
ModuleNotFoundError: No module named 'playwright'
```

`download_review_worker.py`가 import 시점에 `main.services.ecm_download`를 불러오고, `ecm_download.py`가 다시 `playwright.async_api`를 즉시 import하기 때문에 Playwright가 설치되지 않은 환경에서는 기존 dry-run 테스트도 import 단계에서 실패한다.

## Merge 전 필수 수정

1. 의존성 정리

   현재 기준 브랜치의 검증 환경은 Django 5.2 계열로 맞춰져 있다. 검토 대상 브랜치의 `14_dependency_management.md`에는 Django 6.0.5, Python 3.14.4, Playwright 1.59.0 등이 기록되어 있어 실제 서버 적용 기준과 충돌할 수 있다.

   추천 방향: 운영 서버 기준을 Django 5.2 계열로 고정하고, Playwright/pywinauto/pywin32는 별도 runtime requirements에 추가한다. UI 목업용 `requirements-ui.txt`에는 실제 ECM 자동화 의존성을 강제로 넣지 않는 편이 안전하다.

2. optional import 또는 테스트 분리

   Playwright와 pywinauto가 없는 환경에서도 UI/API/dry-run 테스트는 통과해야 한다.

   추천 방향: live automation 모듈 import를 worker 실행 시점으로 늦기거나, live mode 진입 시 명확한 설정 오류를 반환하도록 분리한다. 그래야 목업/CI/문서 검증 환경이 Windows agent 의존성 때문에 깨지지 않는다.

3. ECM 자동화 리소스 정리

   `run_ecm_automation()`은 성공 시 page/context를 닫지 않고, 호출자에게 handle도 반환하지 않는다. 주석은 호출자가 popup 이후 닫는다고 되어 있지만 실제 반환값에는 닫을 수 있는 객체가 없다. 또한 `async_playwright().start()`로 시작한 Playwright driver도 `browser.close()`만으로는 명시적으로 stop되지 않는다.

   추천 방향: 브라우저, context, page의 소유권을 worker에 명확히 두고 `try/finally`로 project 단위 context를 닫는다. Playwright 객체도 worker 종료 시 `stop()`까지 호출한다.

4. 기존 ECM 작업과의 공통 lock

   기준 브랜치에는 기존 WebSocket ECM 작업과 download-review 작업이 같은 ECM/Playwright/clipboard 자원을 동시에 사용하지 않도록 `main/utils/ecm_agent_lock.py`와 `ECM_AGENT_LOCK_PATH`가 있다. 검토 대상 브랜치의 live worker는 `workflow.db`의 `DownloadReviewLock`은 잡지만, 실제 ECM 접근 직전에 공통 파일 lock을 잡는 코드가 확인되지 않았다.

   추천 방향: `run_ecm_automation()`부터 Windows agent popup/전송 완료 확인까지의 구간을 `async_ecm_agent_lock()`으로 감싼다. 기존 기능은 queue 구조를 바꾸지 않고, ECM 실제 접근 직전에만 lock을 잡도록 유지한다.

5. 실패 상태 write-back

   사용자가 정의한 기준은 `보류 = 작업 자체 실패`, `완료 = 모든 점검규칙 통과`, `수정 필요 = 한 개 이상 부적합`이다. 검토 대상 브랜치의 live worker 실패 경로는 프로젝트 실패를 기록하지만 `ecmlist.db`의 `점검결과=보류` write-back이 명확하지 않다.

   추천 방향: 다운로드/agent/검증 단계 실패는 `workflow.db`에 상세 오류를 저장하고, `ecmlist.db`에는 `점검결과=보류`, `점검날짜=현재일`을 반영한다. 단, 다운로드 성공만으로 `완료`를 쓰면 안 된다. `완료`는 실제 점검 규칙 30개가 모두 통과한 뒤에만 쓴다.

6. 다운로드 검증 정책

   검토 대상 브랜치의 `download_verify.py`는 0 byte 파일이나 프로젝트 번호가 포함되지 않은 파일을 발견해도 성공으로 반환할 수 있다.

   추천 방향: 0 byte 파일은 실패로 처리한다. 프로젝트 번호 미포함 파일은 ECM 실제 파일명 규칙을 확인하기 전까지는 경고로 기록하되, 다음 실제 샘플 확보 후 실패 여부를 결정한다.

7. zip 설계와 개별 파일 설계 혼재

   기존 문서와 dry-run 메시지는 zip 다운로드를 기준으로 쓰인 부분이 많지만, 검토 대상 브랜치의 live verify는 다운로드 폴더 안의 개별 파일을 검사하는 흐름이다.

   추천 방향: 실제 DestinyECMAgent가 zip 하나를 만드는지, 여러 파일을 직접 저장하는지 테스트 프로젝트로 먼저 확인한다. 그 결과에 맞춰 `01_automation_flow.md`, `04_agent_download.md`, `05_zip_inspection.md`, `12_implementation_roadmap.md`, `15_open_decisions.md`, `16_download_review_backend_decisions.md`를 한 번에 정리한다.

8. 설정 파일 인코딩

   검토 대상 브랜치의 `myproject/settings.py`는 일부 한국어 주석이 깨져 보이고 BOM이 섞인 것으로 보인다. 또한 `AGENT_DOWNLOAD_BASE_DIR`가 settings에 직접 추가되어 있어 운영 서버별 경로 변경 방식이 아직 명확하지 않다.

   추천 방향: merge 전에 UTF-8 인코딩을 정리하고, 설정 추가분만 최소 diff로 다시 적용한다.

9. 운영 스크립트 정합성

   `start_server.ps1` 문서와 주석에는 Uvicorn 표현이 남아 있지만 실제 명령은 `manage.py runserver`이다. 또한 `runserver`를 `--noreload` 없이 실행하면 PID 파일이 부모 프로세스만 추적하는 문제가 생길 수 있다.

   추천 방향: 개발/테스트용은 `manage.py runserver --noreload`, 운영용은 별도 배포 방식으로 구분한다. 지금 단계에서는 스크립트와 문서 모두 “Django runserver 기반 개발/검증용”이라고 명확히 쓴다.

10. live worker 기본 실행 안전장치

   검토 대상 브랜치의 `run_download_worker`는 `--dry-run`을 붙이지 않으면 live ECM 자동화를 바로 실행한다. `start_worker.ps1`도 `-DryRun`을 생략하면 live mode로 시작한다.

   추천 방향: 다음 merge 전까지는 운영 스크립트 기본값을 dry-run 또는 명시적 live 옵션으로 바꾼다. 실제 운영 전환 시점에만 live 기본값을 허용한다.

11. Windows agent popup 실제 검증

   `agent_popup.py`는 시스템 알림, 전송상황 창, 폴더 선택 창을 처리하지만, 중복 알림이 전송상황 대기보다 먼저 뜨는 경우 타임아웃될 수 있다.

   추천 방향: 실제 ECM에서 테스트 프로젝트 1건으로 visible worker를 실행하고, popup 발생 순서를 로그로 남긴 뒤 상태 머신을 조정한다. `job_id`를 다운로드 경로에 쓰지 않는 현재 방식도 유지할지 결정한다.

## 다음 작업 순서

1. `feature/stages-4-9-automation` 브랜치에서 의존성 파일을 먼저 정리한다.

   추천:

   - `requirements.txt`: 운영 서버 기준 Django 5.2 계열과 공통 runtime 의존성
   - `requirements-automation.txt`: Playwright, pywinauto, pywin32 등 Windows agent 자동화 의존성
   - `requirements-ui.txt`: UI 목업/로컬 확인에 필요한 최소 의존성

2. live automation import 구조를 수정한다.

   목표:

   - Playwright 미설치 환경에서도 `manage.py test main.tests --settings=myproject.ui_mock_settings`가 통과해야 한다.
   - live mode 실행 시 Playwright/pywinauto가 없으면 사용자에게 해석 가능한 오류를 남겨야 한다.

3. worker live mode의 상태 반영을 보강한다.

   목표:

   - 실패: `workflow.db` 상세 오류 저장, `ecmlist.db` `점검결과=보류`
   - 다운로드 성공: 아직 `완료`가 아니라 “다운로드 완료 또는 검증 대기” 상태로 유지
   - 규칙 점검 성공: 모든 규칙 통과 시에만 `완료`
   - 규칙 점검 부적합: 하나라도 부적합이면 `수정 필요`

4. Playwright/pywinauto 실제 테스트 전에 visible 실행 옵션을 운영 스크립트에 추가한다.

   추천 명령:

   ```powershell
   .\.venv\Scripts\python.exe manage.py run_download_worker --once --no-headless
   ```

   `start_worker.ps1`에도 `-NoHeadless` 같은 옵션을 추가하는 것이 좋다.

5. 실제 ECM 테스트는 20:00-07:00 시작 가능 시간 정책을 유지하되, 개발자 수동 테스트용 override는 별도 설정으로 제한한다.

   추천:

   - 기본 API/worker는 시간 제한 준수
   - 관리자 로컬 테스트에서만 `DOWNLOAD_REVIEW_IGNORE_TIME_WINDOW=True` 같은 설정을 허용
   - 이 설정은 운영 기본값 `False`

6. 운영 스크립트와 문서를 맞춘 뒤 merge한다.

   merge 전 최소 검증:

   ```powershell
   .\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
   .\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
   .\.venv\Scripts\python.exe manage.py run_download_worker --once --dry-run --settings=myproject.ui_mock_settings
   .\status.ps1
   ```

## 다음 커밋부터 문서 운영 규칙

앞으로 기능 커밋을 만들 때마다 다음 중 하나를 반드시 갱신한다.

- 계속 이어지는 작업이면 `00_next_step.md`를 갱신한다.
- 큰 단계가 끝나서 기록을 남기고 싶으면 `next_YYYYMMDD_<topic>.md` 형태의 스냅샷 문서를 추가한다.

각 next 문서에는 최소한 다음 항목을 남긴다.

- 현재 브랜치와 기준 커밋
- 이번 커밋에서 바뀐 내용
- 실행한 검증 명령과 결과
- 다음 작업자가 바로 시작할 수 있는 명령
- merge 전 남은 위험
- 결정 필요 항목과 추천 방향

## 결정 필요

1. 운영 서버 Django 기준

   추천: Django 5.2 계열로 고정한다.

   이유: 기존 `settings.py`와 현재 목업 검증 환경이 5.2 계열이고, 6.0.5로 올리면 운영 적용 시 호환성 문제가 추가로 생길 수 있다. ECM/Windows agent 자동화가 이미 위험도가 높은 영역이므로 Django 업그레이드는 별도 작업으로 분리하는 편이 안전하다.

2. 다운로드 성공 상태의 `ecmlist.db` 반영 방식

   추천: 다운로드 성공만으로 `점검결과`를 바꾸지 않는다. 실패만 `보류`로 쓰고, 실제 규칙 점검 결과가 나온 뒤 `완료` 또는 `수정 필요`를 쓴다.

   이유: 사용자가 정한 `완료` 기준은 모든 점검규칙 통과이기 때문에, 다운로드 완료와 점검 완료를 섞으면 UI에서 완료 프로젝트를 다시 요청하지 못하는 문제가 생길 수 있다.

3. 0 byte 파일 처리

   추천: 실패로 처리한다.

   이유: zip 또는 다운로드 산출물이 0 byte라면 사용자가 다시 확인해야 하는 오류 상황에 가깝고, 성공으로 넘기면 이후 점검 결과가 왜 비어 있는지 추적하기 어렵다.

4. 프로젝트 번호가 파일명에 없는 경우

   추천: 실제 샘플 3-5건을 확인하기 전까지는 경고로 기록한다.

   이유: ECM 파일명 규칙이 아직 확정되지 않았기 때문에 바로 실패로 막으면 정상 파일을 잘못 실패 처리할 수 있다. 다만 경고는 결과 상세 팝업에 노출해야 한다.
