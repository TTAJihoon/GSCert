# 남은 고민과 확정 필요 항목

## 목적

다른 대화창이나 이후 작업에서도 현재 설계 상태를 이어갈 수 있도록, 아직 확정되지 않았거나 실제 테스트로 검증해야 하는 항목을 모아 둔다.

이 문서는 작업이 진행될 때마다 갱신한다.

## 현재 진행 상태

현재 브랜치:

```text
codex-job-runner-persistence
```

현재까지 완료:

- 자동화 전체 흐름 설계 문서화
- DB, worker, 운영 스크립트, UI/API 설계 문서화
- mock 데이터 기반 `/download-review/` UI 구현
- `ecmlist.db`/`ecm_list` 기준 프로젝트 목록 API 연동
- `workflow.db` 작업/락/상태 저장 모델과 dry-run worker command 구현
- 기존 ECM WebSocket 자동화와 download-review worker 사이의 공통 lock 구현
- 점검 결과를 `ecmlist.db`의 점검 컬럼에 반영하는 write-back 서비스 구현
- 결과 조회 탭 API 연동
- 폴더별 `readme.md` 작성 정책 정리
- dependency 관리 문서 추가
- 4단계 운영 스크립트 구현: `start_server.ps1`, `stop_server.ps1`, `start_worker.ps1`, `stop_worker.ps1`, `start_all.ps1`, `stop_all.ps1`, `status.ps1`
- 5단계 웹페이지1 자동화 구현: `ecm_download.py`, `ecm_selectors.py` 생성, worker에 실제 ECM 자동화 연결, `--no-headless` 옵션 추가
- 6+7+8단계 통합 구현: ECM 트리 구조 반영, `agent_popup.py` 생성(새 폴더 만들기/전송현황/시스템알림), worker 파이프라인 연결
- 9단계 구현: `download_verify.py` 생성(다운로드 파일 존재/개수/크기 확인)
- 기준 데이터 흐름 정리: `reference.xlsx`를 원본으로 보고 `manage.py sqlite`가 `reference.db`를 생성하도록 정리
- 기준 데이터 Git 반영: `manage.py sqlite` 기본 실행 시 `reference.xlsx`와 `reference.db` 변경분만 commit/push하도록 구현
- `weekly.py`에서 외부 `db.bat` 대신 저장소 안의 `manage.py sqlite`를 직접 호출하도록 정리

아직 실제 구현 전/검증 전:

- 5~9단계 실제 서버에서의 통합 검증 (ECM 접속 → 다운로드 → 팝업 처리 → 파일 확인)
- zip 내부 검사 규칙
- 실제 규칙 결과와 `ecmlist.db` 산출물 컬럼 간 매핑

## 우선순위 높은 미확정 항목

### 1. UI 목업 검토

현재 `/download-review/`는 `ecmlist.db` 프로젝트 목록, 작업 요청/진행 API, 결과 조회 API를 사용한다.

확정 필요:

- 프로젝트 목록 컬럼이 충분한지
- 검색/필터 조건이 적절한지
- 선택 요약 위치와 표시 방식이 편한지
- 예약/대기/진행 중에도 작업 요청이 등록되는 흐름이 이해되는지
- 진행상황 메시지가 실제 업무자가 이해하기 쉬운지
- 결과 조회 화면에서 실패 프로젝트를 찾기 쉬운지
- 화면 밀도, 크기, 색상, 버튼 위치가 적절한지

관련 문서:

- `13_ui_mockup_design.md`
- `08_ui_api_design.md`

### 2. ecmlist.db 생성 방식

프로젝트 기준 DB는 사용자가 따로 생성한다.

현재 반영:

- 기준 DB 위치는 `main/data/ecmlist.db`다.
- 기준 테이블은 `ecm_list`다.
- `번호`부터 `시험PL`까지는 기준정보로 보고 수정하지 않는다.
- 점검 결과에 따라 `점검결과`부터 `홍보이미지`까지의 점검 컬럼만 수정 대상으로 본다.
- `main/utils/ecmList/sync_sheets.py`를 Google Sheets에서 기준 프로젝트를 추가하는 수동 실행 유틸로 둔다.
- `credentials.json`, `token.json`은 로컬 인증 파일이므로 Git에 올리지 않는다.

추가 확정 필요:

- 프로젝트 목록 갱신을 수동 실행만 유지할지, 추후 관리자 버튼/스케줄러로 연결할지
- 실제 규칙 구현 시 각 점검규칙을 어느 산출물 컬럼에 매핑할지

관련 문서:

- `02_database_design.md`
- `12_implementation_roadmap.md`

### 3. reference.xlsx 운영 반영 방식

기존 운영 흐름은 유지한다.

현재 반영:

- `main/data/reference.xlsx`는 ECM 원천 데이터를 누적 관리하는 기준 원본이다.
- `main/data/reference.db`는 `reference.xlsx`에서 생성되는 조회용 SQLite DB다.
- `main/management/commands/sqlite.py`는 기본 입력/출력을 `reference.xlsx`/`reference.db`로 사용한다.
- `manage.py sqlite` 기본 실행은 DB 생성 후 기준 데이터 변경분을 Git commit/push한다.
- `manage.py sqlite --no-git-sync`는 Git 반영 없이 DB 생성만 수행한다.
- `weekly.py`는 ECM 원천 파일 append 후 `manage.py sqlite`를 직접 호출한다.
- 새 스케줄러는 추가하지 않았고, 기존 Windows 작업 스케줄러 또는 배치 파일이 `weekly.py`를 실행할 때만 동작한다.
- `GSCERT_SQLITE_NO_GIT_SYNC=1`을 설정하면 weekly 흐름에서도 Git 반영을 생략할 수 있다.

추가 확정 필요:

- 운영 weekly 실행에서 Git push까지 기본 수행할지, 운영 서버에만 `GSCERT_SQLITE_NO_GIT_SYNC=1`을 둘지
- 운영 서버에서 `GSCERT_PYTHON`, `GSCERT_DJANGO_SETTINGS` 환경변수 지정이 필요한지

관련 문서:

- `main/data/README.md`
- `10_operations_scripts.md`
- `16_download_review_backend_decisions.md`

### 4. workflow.db 세부 스키마

실행 이력 DB는 `ecmlist.db`와 분리한다.

현재 반영:

- 파일명은 `main/data/workflow.db`로 확정했다.
- Django ORM 모델과 별도 DB alias 방식으로 관리한다.
- download-review 전용 모델은 `main` 앱에 두고, database router로 `workflow.db`에만 저장한다.
- 작업/프로젝트/점검규칙/점검결과/로그/락 테이블의 1차 스키마를 구현했다.

추가 검증 필요:

- stale running 작업 복구 기준
- 실제 worker 구현 중 필요한 컬럼 보강 여부

관련 문서:

- `02_database_design.md`
- `06_recovery_and_lock.md`
- `09_worker_process_design.md`

### 5. worker 운영 방식

별도 worker 프로세스 방식은 확정했고, `run_download_worker` command 골격과 dry-run을 구현했다.

4단계에서 구현 완료:

- `start_server.ps1`, `stop_server.ps1`: Uvicorn PID/포트 관리
- `start_worker.ps1`, `stop_worker.ps1`: worker PID 관리, `-DryRun`/`-Once` 스위치 지원
- `start_all.ps1`, `stop_all.ps1`: 통합 시작/중지
- `status.ps1`: PID/포트/workflow.db 활성작업/heartbeat 표시

확정/검증 필요:

- 개발/검증 단계에서 worker 창을 보이게 실행할지
- 운영에서 `-WindowStyle Hidden` 사용 시 GUI 팝업 제어가 가능한지
- RDP 세션 종료 상태에서 자동화가 유지되는지
- 서버 잠금 화면에서 폴더 선택 팝업 제어가 가능한지
- worker graceful shutdown이 필요한지

관련 문서:

- `09_worker_process_design.md`
- `10_operations_scripts.md`

### 6. 웹페이지1 자동화 실제 검증

웹페이지1 주소:

```text
http://210.96.71.85
```

실제 ECM 트리 구조 (확정):

```text
전사 폴더 > 상암AX센터 (초기 펼침)
  > {연도}년 시험서비스 (예: 2026년 시험서비스)
    > 01 GS인증시험(1등급)
      > 프로젝트 폴더 (예: 00009 TTA-26-00009(완료) 회사명(제품명))
```

시험 유형 폴더: `01 GS인증시험(1등급)`, `02 V&V 시험`, `03 KPaaS 시험` (01번만 사용)

현재 확인된 selector:

```text
프로젝트 폴더 영역: #edm-folder
전체 선택 체크박스: #main-list-document > table > thead > tr > th.document-list-header-checkbox > input[type=checkbox]
고급 메뉴 버튼: #menu-folder-list-drop
파일 다운로드 메뉴: #edm-main-context-menu li[menuevent="saveDocumentsFileAll"]
```

확정/검증 필요:

- 프로젝트번호 `TTA-26-00009`로 항상 정확한 폴더를 찾을 수 있는지
- 프로젝트 폴더가 트리에서 접혀 있을 때 검색/확장 방식
- 문서 목록 로딩 완료 판단 기준
- 문서 목록이 비어 있는 경우 처리
- 파일 다운로드 메뉴 클릭 후 폴더 찾아보기 창 표시까지 평균 소요 시간

관련 문서:

- `03_webpage1_automation.md`

### 7. Windows 폴더 선택 팝업 자동화

개발 PC 다운로드 경로:

```text
C:\Users\jh910\Downloads
```

운영에서는 설정값 사용:

```text
AGENT_DOWNLOAD_BASE_DIR
```

확정/검증 필요:

- `폴더 찾아보기` 창을 pywinauto로 안정적으로 찾을 수 있는지
- `다운로드` 폴더 아래 프로젝트 폴더를 트리 클릭으로 선택할 수 있는지
- 미리 만든 폴더를 선택할지, 팝업에서 새 폴더 만들기를 누를지
- 폴더명이 긴 경우 트리에서 표시/선택 문제가 없는지
- 폴더 선택 실패 시 재시도 정책

관련 문서:

- `04_agent_download.md`

### 8. 전송현황/시스템 알림 처리

작업 관리자에서 확인된 에이전트:

```text
DestinyECMAgent(32비트)
```

다운로드 중 창:

```text
전송현황
```

중복 파일 알림 창:

```text
시스템 알림
```

확정/검증 필요:

- `전송현황` 창 제목/클래스/프로세스를 pywinauto로 식별 가능한지
- 창이 사라지는 시점이 실제 다운로드 완료와 일치하는지
- zip 파일 크기 안정화 대기 시간이 필요한지
- `시스템 알림` 문구와 버튼 구조
- 중복 발생 시 폴더 변경 후 재시도 흐름
- 재시도 최대 횟수

관련 문서:

- `04_agent_download.md`
- `06_recovery_and_lock.md`

### 9. 다운로드 파일 확인

확정 사항:

- 다운로드는 zip이 아니라 개별 파일들이 각각 다운로드된다.
- 파일명에 프로젝트번호가 포함되는 경우가 대부분이나 예외도 있다.
- 폴더 찾아보기에서 '새 폴더 만들기' 후 프로젝트번호를 입력하여 폴더를 생성한다.

구현 완료:

- `download_verify.py`: 폴더 존재, 파일 개수, 0바이트 확인, 프로젝트번호 포함 여부

검증 필요:

- 실서버에서 실제 다운로드 파일 확인

관련 문서:

- `04_agent_download.md`
- `05_zip_inspection.md`

### 10. 검사 규칙 설계

검사 규칙 상세 설계는 마지막 단계로 보류했다.

예상 규칙:

- Excel 머리글 또는 특정 셀의 프로젝트번호 확인
- Word 표의 특정 위치 값 확인
- 파일명에 프로젝트번호 포함 확인
- 필수 파일 존재 여부 확인
- 파일 저장시간 또는 수정시간 확인

확정 필요:

- 규칙 저장 방식을 DB + JSON으로 할지
- 규칙 버전 관리 방식
- 검사 결과 상태값
- 규칙별 심각도
- 결과 화면에서 규칙별 drill-down 방식

관련 문서:

- `05_zip_inspection.md`
- `07_skill_strategy.md`

### 11. dependency와 requirements 정리

현재 의존성은 `14_dependency_management.md`에 기록했다.

현재 반영:

- `requirements.txt`는 Django 5.2 계열 기준으로 정리했다.
- Windows 자동화 의존성은 `requirements-automation.txt`로 분리했다.
- UI 목업/로컬 실행 의존성은 `requirements-ui.txt`를 유지한다.

추가 확인 필요:

- 운영 서버에서 실제 서버 실행에 사용하는 패키지 목록과 `requirements.txt`의 차이
- 운영 서버 시작 방식이 Uvicorn인지 Django runserver 래퍼인지

관련 문서:

- `14_dependency_management.md`

## 다음 작업 후보

1. 5~9단계 통합 검증: 실제 ECM 서버에서 전체 다운로드 파이프라인 테스트
2. 실제 다운로드 산출물 기준으로 점검 규칙과 `ecmlist.db` 점검 컬럼 매핑 정의
3. 결과 조회 화면에 실제 점검 규칙 결과와 상세 오류를 연결
4. 테스트가 끝나면 download-review 시작 가능 시간을 `20:00-07:00`으로 복구

## 대화 재개 시 추천 질문

다른 대화창에서 이어갈 때는 아래처럼 시작하면 된다.

```text
GSCert 저장소의 codex-job-runner-persistence 브랜치에서 이어서 진행하자.
15_open_decisions.md를 먼저 읽고 현재 남은 결정사항을 기준으로 다음 단계를 정리해줘.
```
