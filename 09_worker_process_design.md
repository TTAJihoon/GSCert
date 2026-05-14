# 별도 worker 프로세스 설계

## 결론

다운로드와 검사 작업은 Django/Uvicorn 웹서버 내부 스레드가 아니라 별도 worker 프로세스에서 실행한다.

## 이유

웹서버는 화면/API/상태 조회를 담당하고, worker는 장기 작업과 Windows 에이전트 자동화를 담당한다.

이렇게 분리하면 웹서버 재시작, 요청 처리, 장기 다운로드 작업의 장애 범위를 분리할 수 있다.

## 프로세스 구조

```text
Uvicorn 프로세스
└─ 프로젝트 목록 조회
└─ 작업 생성 API
└─ 진행상황 조회 API
└─ 결과 조회 API

download_worker 프로세스
└─ workflow.db에서 pending 작업 확인
└─ 작업 락 획득
└─ 웹페이지1 자동화 (main/views/review/ecm_download.py, main/views/review/ecm_selectors.py)
└─ 에이전트 다운로드 팝업 처리 (main/views/review/ecm_agent_popup.py)
└─ 다운로드 파일 확인 (main/views/review/ecm_download_verify.py)
└─ 검사 실행
└─ 작업 상태 저장
```

## 운영 파일 구조

운영 서버 기준:

```text
C:\GSCert
├─ start_server.ps1
├─ stop_server.ps1
├─ start_worker.ps1
├─ stop_worker.ps1
├─ logs
│  ├─ uvicorn_YYYYMMDD_HHMMSS_out.log
│  ├─ uvicorn_YYYYMMDD_HHMMSS_err.log
│  ├─ download_worker_YYYYMMDD_HHMMSS_out.log
│  └─ download_worker_YYYYMMDD_HHMMSS_err.log
├─ run
│  ├─ uvicorn.pid
│  └─ download_worker.pid
└─ myproject
```

## worker 실행 명령

worker는 Django management command로 실행한다.

```powershell
C:\GSCert\.venv\Scripts\python.exe manage.py run_download_worker
# (운영 서버에서는 start_worker.ps1이 .venv/venv 자동 폴백 처리)
```

예상 파일 위치:

```text
main/management/commands/run_download_worker.py
```

초기 구현은 dry-run을 먼저 제공한다.

```powershell
python manage.py run_download_worker --once --dry-run
```

dry-run은 ECM 접속, Playwright, zip 다운로드 없이 `workflow.db` 상태 전이와 점검결과 저장만 검증한다.

## worker 시작 스크립트

`start_worker.ps1`은 기존 Uvicorn 시작 스크립트와 같은 방식으로 만든다.

차이점:

- PID 파일: `run/download_worker.pid`
- 로그 파일: `logs/download_worker_*.log`
- 실행 명령: `python manage.py run_download_worker`
- worker가 이미 실행 중이면 새로 시작하지 않는다.
- 개발/검증 단계에서는 창을 보이게 실행할 수 있고, 운영에서는 `-WindowStyle Hidden`을 사용한다.

## worker 중지 스크립트

`stop_worker.ps1`은 `download_worker.pid`를 읽어 해당 프로세스를 종료한다.

중지 시 정책:

1. 가능한 정상 종료 신호를 보낸다.
2. 일정 시간 후에도 살아 있으면 강제 종료한다.
3. PID 파일을 정리한다.
4. workflow.db의 running 작업은 다음 시작 시 재개 정책에 따라 처리한다.

상세 운영 스크립트 정책은 `10_operations_scripts.md`에서 관리한다.

## worker 루프

worker는 아래 과정을 반복한다.

```text
1. workflow.db에서 pending 또는 재개 대상 작업 조회
2. automation_lock 획득 시도
3. 작업 상태를 running으로 변경
4. heartbeat 갱신 시작
5. 프로젝트 목록을 순서대로 처리
6. 프로젝트별 상태와 결과 저장
7. 작업 완료 또는 실패 상태 저장
8. lock 해제
9. 다음 작업 대기
```

## heartbeat

worker가 살아 있는지 판단하기 위해 주기적으로 heartbeat를 DB에 저장한다.

추천 컬럼:

```text
automation_job.worker_heartbeat_at
automation_job.worker_pid
automation_job.worker_host
```

권장 갱신 주기:

```text
10초 ~ 30초
```

heartbeat 용도:

- worker가 죽었는데 작업이 running으로 남는 상황 감지
- 서버 재시작 후 재개 대상 판단
- 관리자 화면에서 worker 상태 표시

## stale running 작업 판단

작업 상태가 running인데 heartbeat가 일정 시간 이상 갱신되지 않으면 stale 상태로 본다.

초기 권장값:

```text
heartbeat 미갱신 5분 이상
```

stale 작업 처리 정책:

1. 이미 completed인 프로젝트는 건너뛴다.
2. running 상태였던 프로젝트는 pending 또는 failed로 되돌린다.
3. 작업은 재개 대상으로 표시한다.
4. worker가 다시 시작되면 남은 프로젝트부터 처리한다.

## 단일 worker 보장

worker는 동시에 1개만 실행되어야 한다.

보호 장치:

- `download_worker.pid` 확인
- workflow.db의 `automation_lock` 확인
- worker 시작 시 기존 PID 프로세스 생존 여부 확인
- worker 루프에서 lock 획득 실패 시 작업 처리하지 않음

## GUI 자동화 관련 위험

에이전트가 Windows 팝업을 띄우기 때문에 worker는 실제 로그인된 Windows 사용자 세션에서 실행되어야 할 가능성이 높다.

위험요소:

- Windows 서비스로 실행하면 GUI 팝업을 제어하지 못할 수 있다.
- RDP 세션이 끊기면 GUI 자동화가 실패할 수 있다.
- 서버가 잠금 화면 상태면 폴더 선택 팝업 자동화가 실패할 수 있다.
- `Start-Process -WindowStyle Hidden`으로 실행한 worker가 GUI 팝업에 접근 가능한지 테스트가 필요하다.

초기 운영 권장:

- Windows 서비스 등록보다 PowerShell 시작 스크립트 사용
- 로그인된 사용자 세션에서 worker 실행
- 실제 서버에서 폴더 찾아보기/전송현황/시스템 알림 자동화 테스트

## Django 내부 스레드와 비교

Django 내부 스레드는 구현이 빠르지만 Uvicorn 재시작과 함께 작업이 죽고, 웹 요청 처리와 Windows 자동화가 같은 프로세스에 섞인다.

현재 프로젝트는 다운로드 시간이 길고 Windows 에이전트 팝업 자동화가 필요하므로 별도 worker 프로세스가 더 안전하다.

## Celery/RQ와 비교

Celery/RQ는 장기 작업의 표준 구조지만 Redis 같은 추가 인프라가 필요하다.

현재 요구사항은 항상 하나의 작업만 실행하면 되므로 Celery/RQ는 초기 구현에는 과하다.

## 남은 검증 항목

- worker를 `Start-Process -WindowStyle Hidden`으로 실행해도 Windows 팝업 제어가 가능한지
- RDP 세션 종료 상태에서 자동화가 동작하는지
- 서버 잠금 화면에서 자동화가 동작하는지
- worker 강제 종료 후 stale running 작업이 정상 재개되는지
