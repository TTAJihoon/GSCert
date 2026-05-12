# Download Review 백엔드 결정사항

## 목적

`/download-review/` UI 목업에서 확정한 동작과 백엔드 구현 방향을 이어가기 위한 결정 로그다.

## 실행 정책

- 프로젝트 zip 검토 작업은 사용자가 언제든 요청할 수 있다.
- 실제 작업 시작 가능 시간은 20:00부터 07:00까지다.
- 06:59에는 새 작업을 시작할 수 있다.
- 07:00 이후에는 새 작업을 시작하지 않고 다음 실행 가능 시간까지 예약 상태로 둔다.
- 이미 진행 중인 프로젝트는 07:00이 지나도 끝까지 진행한다.
- 시간 제한은 download-review 작업에만 적용한다.
- 기존 WebSocket 기반 ECM URL 조회 기능은 시간 제한 없이 유지한다.

## 동시 실행과 lock

- download-review 작업의 동시 실행 job은 1개다.
- 대기열은 요청 순서로 처리한다.
- 대기열 최대 job 수는 5개다.
- 대기 중인 작업은 취소할 수 있다.
- 기존 WebSocket ECM 작업과 download-review 작업은 같은 ECM/Playwright/clipboard 리소스를 사용할 수 있으므로 `ecm_agent` 공통 lock을 적용한다.
- 기존 기능 영향 최소화를 위해 기존 WebSocket 작업의 queue 구조는 유지하고, ECM 접근 직전에만 lock을 획득한다.
- 캐시 hit처럼 ECM에 실제 접근하지 않는 경로는 lock을 잡지 않는다.

## API 방식

- 조회는 GET을 사용한다.
- 상태를 변경하는 작업 요청, 취소, 재시도는 POST를 사용한다.
- 진행상황은 초기 구현에서 polling을 사용한다.
- 권한/로그인 기능은 현재 없으므로 누구든 작업 요청과 조회를 할 수 있다.
- 보안을 위해 프로젝트번호 형식 검증, query allowlist, SQL parameter binding, 내부 stack trace 비노출을 적용한다.
- 현재 다른 작업이 진행 중이어도 작업 요청은 받을 수 있으며, 새 작업은 `예약됨` 상태로 등록한다.

## DB 정책

- 기준 DB 위치는 `main/data/ecmlist.db`다.
- 기준 DB 테이블명은 `ecm_list`다.
- `ecmlist.db`는 반드시 존재해야 하며 없으면 오류다.
- 프로젝트번호 컬럼은 `프로젝트번호`이고 유일값이다.
- 인증일자 컬럼은 `인증일자`이며 날짜 포맷은 `05/12` 형태다.
- 괄호나 슬래시가 포함된 SQLite 컬럼명은 사용할 수 있지만 SQL에서 반드시 식별자 quoting 또는 alias map으로 접근한다.
- 서버 실행 중 `ecmlist.db`를 덮어쓰지 않는 운영을 기본으로 한다.
- 작업 생성 시점의 ecm row는 `ecm_row_json` snapshot으로 `workflow.db`에 저장한다.
- `workflow.db` 위치는 `main/data/workflow.db`다.
- `workflow.db`는 Django ORM과 별도 DB alias 방식으로 관리한다.
- download-review 전용 모델은 `main` 앱에 두고, database router로 `workflow.db`에만 migrate한다.
- 기존 `main.Job` 모델은 의미가 다르므로 download-review 작업 이력에는 재사용하지 않는다.
- 30개 내외 점검규칙 결과는 프로젝트별 별도 결과 테이블에 저장한다.

## 상태 정책

- DB에는 영문 code를 저장하고 UI에는 한글 label을 표시한다.
- 작업 상태 label: 예약됨, 대기중, 진행중, 완료, 실패, 취소
- 프로젝트 상태 label: 대기중, 진행중, 다운로드완료, 검사중, 완료, 실패, 보류, 건너뜀
- 점검결과 label: 정상, 부적합, 경고, 오류
- UI의 프로젝트 점검결과에서 `완료`는 모든 점검규칙을 통과한 경우에만 부여한다.
- 점검규칙 중 하나라도 부적합이면 `수정 필요`로 표시한다.
- `보류`는 점검 규칙 결과가 아니라 작업 자체가 실패한 경우에 사용한다.

## heartbeat와 재시도

- worker heartbeat는 30초마다 갱신한다.
- 2분 이상 미갱신 시 경고로 표시한다.
- 5분 이상 미갱신 시 stale/복구 대상으로 판단한다.
- 프로젝트별 재시도는 최대 2회다.
- 재시도 가능 후보 단계는 폴더 선택 팝업 실패, 중복 파일 알림 처리 실패, 전송현황 창 대기 timeout, zip 생성 대기 timeout, zip 크기 안정화 실패다.

## 파일과 로그 보관

- 다운로드된 zip 파일은 분석 완료 후 삭제한다.
- 실패, 중복, 부분 다운로드 파일도 분석 또는 실패 처리 후 삭제한다.
- 작업 로그와 결과 이력은 영구 보관한다.
- 사용자에게 보여줄 파일 경로는 서버 전체 경로가 아니라 프로젝트 번호가 적힌 폴더부터 표시한다.
- 스크린샷 경로는 사용자에게 보여주지 않고 파일명만 표시한다.
- 내부 stack trace는 관리자 로그에만 저장한다.

## 구현 반영 사항

- `myproject.settings.DATABASES.workflow` alias를 추가했다.
- `main.db_routers.WorkflowDatabaseRouter`로 download-review 전용 모델만 `workflow.db`에 저장한다.
- `automation_job`, `automation_job_project`, `inspection_rule`, `inspection_result`, `automation_log`, `automation_lock` 테이블을 Django 모델로 정의했다.
- 기존 WebSocket ECM 작업은 캐시 miss 후 실제 ECM/clipboard 접근 직전에 `ecm_agent.lock` 파일 lock을 획득한다.
- `ecmlist.db` 조회는 `main.services.reference_db`에서 read-only SQLite 연결로 처리한다.
- `main/utils/ecmList/sync_sheets.py`는 Google Sheets 기준정보를 `main/data/ecmlist.db`의 `ecm_list` 테이블에 추가 동기화하는 수동 실행 유틸이다.
- `main/utils/ecmList/credentials.json`, `main/utils/ecmList/token.json`은 로컬 인증 파일이므로 Git에 올리지 않는다.
- `번호`부터 `시험PL`까지는 기준정보로 취급하고, 점검 후에는 `점검결과`부터 `홍보이미지`까지의 점검 컬럼만 갱신 대상으로 본다.
- `main.services.reference_db.write_project_review_result()`는 allowlist에 있는 점검 컬럼만 갱신하며, `회사명` 같은 기준정보 컬럼 갱신 요청은 거부한다.
- write-back 연결은 SQLite `mode=rw`를 사용해 DB가 없을 때 새 파일을 만들지 않는다.
- write-back은 `프로젝트번호` 갱신 rowcount가 정확히 1건일 때만 성공으로 처리한다. 0건 또는 중복 행은 rollback 후 오류로 처리한다.
- dry-run worker는 프로젝트 처리 완료 시 `ecmlist.db`에 `점검결과`를 반영한다: 모든 규칙 통과는 `완료`, 부적합 규칙 존재는 `수정 필요`, 작업 자체 실패는 `보류`.
- dry-run worker의 산출물 점검 컬럼은 샘플 값으로 갱신한다: 통과는 `정상`, 부적합 샘플은 `부적합`, 보류 프로젝트는 `X`.
- `GET /api/projects/`를 구현했다.
- 프로젝트 목록 기본 정렬은 `인증일자` 최신순, 같은 날짜는 `프로젝트번호` 내림차순이다.
- 프로젝트 목록 API는 allowlist query parameter만 허용한다.
- `POST /api/jobs/`를 구현했다.
- 이미 예약됨/대기중/진행중인 프로젝트가 포함된 새 작업 요청은 전체 실패 처리한다.
- `완료` 프로젝트가 포함된 작업 요청은 버그/우회 요청으로 보고 전체 실패 처리한다.
- active job은 최대 5개까지 허용한다.
- polling 기반 조회 API를 구현했다: `GET /api/jobs/active/`, `GET /api/jobs/{job_id}/`, `GET /api/jobs/{job_id}/projects/`, `GET /api/job-projects/{job_project_id}/results/`
- 진행/예약/대기 작업이 없으면 API가 `polling.should_poll=false`를 반환한다.
- 권장 polling 주기는 진행중/대기중 3초다.
- 예약됨 상태는 반복 polling하지 않고 `polling.wake_at` 시각에 한 번 다시 조회한다.
- `main/management/commands/run_download_worker.py`에 worker command 골격을 구현했다.
- `python manage.py run_download_worker --once --dry-run`으로 시작 가능한 작업 1개를 dry-run 처리할 수 있다.
- dry-run은 프로젝트 결과를 `완료`, `수정 필요`, `보류`가 섞이도록 저장하고 `ecmlist.db` 점검 컬럼에 write-back한다.

## 다음 구현 순서 추천

1. 결과 조회 탭 API 연동
2. 실제 ECM 다운로드 worker 구현
