# 운영 스크립트 설계

## 목적

Uvicorn 웹서버와 download_worker를 Windows 서버에서 안정적으로 시작, 중지, 상태 확인할 수 있도록 PowerShell 스크립트를 분리한다.

## 확정된 서버 경로

```powershell
$RootDir    = "C:\GSCert"
$AppRootDir = "C:\GSCert\myproject"
$VenvPython = "C:\GSCert\.venv\Scripts\python.exe"
# (없으면 venv\Scripts\python.exe로 폴백)
```

`manage.py`는 `$AppRootDir` 아래에 있는 것으로 전제한다.

## 스크립트 목록

개별 제어:

```text
start_server.ps1
stop_server.ps1
start_worker.ps1
stop_worker.ps1
```

통합 제어:

```text
start_all.ps1
stop_all.ps1
status.ps1
```

## 로그와 PID 파일

공통 디렉터리:

```powershell
$LogsDir = Join-Path $RootDir "logs"
$RunDir  = Join-Path $RootDir "run"
```

서버:

```powershell
$ServerPidFile = Join-Path $RunDir "uvicorn.pid"
```

worker:

```powershell
$WorkerPidFile = Join-Path $RunDir "download_worker.pid"
```

로그 파일:

```text
logs/uvicorn_YYYYMMDD_HHMMSS_out.log
logs/uvicorn_YYYYMMDD_HHMMSS_err.log
logs/download_worker_YYYYMMDD_HHMMSS_out.log
logs/download_worker_YYYYMMDD_HHMMSS_err.log
```

## start_server.ps1

현재 사용 중인 서버 시작 스크립트를 유지한다.

핵심 정책:

- `uvicorn.pid`가 있고 프로세스가 살아 있으면 시작하지 않는다.
- 포트 `8000`이 이미 점유되어 있으면 시작하지 않는다.
- `Start-Process`로 백그라운드 실행한다.
- 운영에서는 `-WindowStyle Hidden`을 사용한다.

## stop_server.ps1

현재 사용 중인 `stop.ps1` 방식을 유지한다.

핵심 정책:

- `uvicorn.pid` 기반으로 프로세스를 종료한다.
- PID 파일은 종료 성공 여부와 무관하게 정리한다.
- 포트 `8000` 점유 프로세스를 추가 확인하고 종료한다.
- 포트 해제 여부를 재확인한다.

## start_worker.ps1

worker 시작 스크립트는 서버 시작 스크립트와 같은 패턴으로 작성한다.

worker 실행 명령:

```powershell
$ArgumentList = @(
  "manage.py",
  "run_download_worker"
)
```

초기 검증 단계에서는 아래처럼 dry-run으로 실행한다.

```powershell
$ArgumentList = @(
  "manage.py",
  "run_download_worker",
  "--once",
  "--dry-run"
)
```

Start-Process 예:

```powershell
$process = Start-Process -FilePath $VenvPython `
                         -ArgumentList $ArgumentList `
                         -WorkingDirectory $AppRootDir `
                         -WindowStyle Hidden `
                         -RedirectStandardOutput $OutLog `
                         -RedirectStandardError  $ErrLog `
                         -PassThru
```

핵심 정책:

- `download_worker.pid`가 있고 프로세스가 살아 있으면 시작하지 않는다.
- 유령 PID 파일은 정리한다.
- worker 로그는 Uvicorn 로그와 분리한다.
- worker 시작 후 PID를 `download_worker.pid`에 저장한다.

## stop_worker.ps1

worker 중지 스크립트는 PID 파일 기반으로 종료한다.

서버와 달리 worker는 특정 포트를 점유하지 않으므로 포트 검사는 하지 않는다.

핵심 정책:

- `download_worker.pid` 기반으로 프로세스를 종료한다.
- PID 파일은 정리한다.
- 종료 후 workflow.db의 running 작업은 worker 재시작 시 재개 정책으로 처리한다.

초기 구현은 `Stop-Process -Force`를 사용할 수 있다.

추후 개선:

- 정상 종료 플래그 파일 또는 DB 플래그를 두고 graceful shutdown 지원
- 현재 프로젝트 처리 단위가 끝난 뒤 종료

## start_all.ps1

서버와 worker를 한 번에 시작한다.

권장 순서:

1. `start_server.ps1`
2. `start_worker.ps1`

서버 API가 뜨지 않아도 worker는 DB 기반으로 동작할 수 있지만, 운영자가 확인하기 쉽도록 서버를 먼저 시작한다.

## stop_all.ps1

서버와 worker를 한 번에 중지한다.

권장 순서:

1. `stop_worker.ps1`
2. `stop_server.ps1`

worker가 Windows 에이전트 팝업을 제어할 수 있으므로 worker를 먼저 중지한다.

## status.ps1

서버와 worker 상태를 함께 표시한다.

표시 항목:

- Uvicorn PID 파일 존재 여부
- Uvicorn PID 프로세스 생존 여부
- 포트 8000 점유 여부
- download_worker PID 파일 존재 여부
- download_worker PID 프로세스 생존 여부
- workflow.db의 active job 여부
- worker heartbeat 시각

## 개발/검증과 운영 실행 방식

개발/검증:

- worker 창을 보이게 실행하는 방식을 허용한다.
- Windows 폴더 찾아보기, 전송현황, 시스템 알림 제어가 실제로 되는지 눈으로 확인한다.

운영:

- 서버와 worker 모두 `-WindowStyle Hidden` 사용
- 로그 파일로 상태 확인
- `status.ps1`로 PID/포트/heartbeat 확인

## 기준 데이터 갱신 흐름

기존 운영 흐름은 유지한다.

1. `main/utils/weekly.py`가 ECM 원천 데이터를 내려받아 `main/data/reference.xlsx`를 갱신한다.
2. `manage.py sqlite`가 `reference.xlsx`를 `main/data/reference.db`로 적재한다.
3. 기준 데이터가 바뀐 경우 `manage.py sqlite`가 `reference.xlsx`와 `reference.db`만 Git commit/push한다.

`weekly.py`는 이 명령을 직접 호출하므로 외부 `db.bat`가 없어도 기준 DB를 갱신할 수 있다. 현재 weekly 흐름은 서버 종료/시작용 `exit.bat`, `run.bat`를 호출하지 않고 `ECM 다운로드 -> reference.xlsx 업데이트 -> reference.db 업데이트`만 수행한다.

수동 실행:

```powershell
.\.venv\Scripts\python.exe manage.py sqlite
```

로컬 검증처럼 Git 반영 없이 DB 생성만 확인할 때:

```powershell
.\.venv\Scripts\python.exe manage.py sqlite --no-git-sync
```

이 흐름은 새 자동화 스케줄을 추가하지 않는다. 스케줄 여부는 기존 운영 배치나 Windows 작업 스케줄러 설정에서 관리한다.

운영 환경별 경로는 아래 환경변수로 조정할 수 있다.

```text
GSCERT_REFERENCE_XLSX
GSCERT_WEEKLY_DOWNLOAD_DIR
GSCERT_EDM_STORAGE_STATE
GSCERT_PYTHON
GSCERT_MANAGE_PY
GSCERT_DJANGO_SETTINGS
GSCERT_SQLITE_NO_GIT_SYNC
```

## 위험요소

- worker를 강제 종료하면 현재 처리 중 프로젝트가 중간 상태로 남을 수 있다.
- worker가 꺼졌는데 `download_worker.pid`가 남는 유령 PID 상황이 생길 수 있다.
- Windows GUI 팝업 자동화는 로그인 세션 상태에 영향을 받을 수 있다.
- `Start-Process -WindowStyle Hidden` 상태에서 GUI 팝업 제어가 가능한지 실제 서버에서 검증해야 한다.

## 문서와 코드 동기화

운영 스크립트가 변경되면 이 문서를 함께 갱신한다.

worker 실행 명령이나 PID 파일명이 바뀌면 아래 문서도 함께 확인한다.

- `09_worker_process_design.md`
- `06_recovery_and_lock.md`
- `08_ui_api_design.md`
