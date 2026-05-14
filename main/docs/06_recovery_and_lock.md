# 락, 실패, 재개 정책

## 단일 작업 락

동시에 하나의 작업만 실행한다.

새 작업 요청 시 실행 중 작업이 있으면 새 작업을 만들지 않고 안내 메시지를 반환한다.

예:

```text
현재 다른 사용자의 작업이 진행 중입니다. 완료 후 다시 요청해 주세요.
```

## 상태값 초안

작업 상태:

- pending
- running
- completed
- failed
- canceled

프로젝트 상태:

- pending
- running
- downloaded
- inspecting
- completed
- failed
- skipped

검사 결과 상태:

- pass
- fail
- warning
- error

## 실패 정책

프로젝트 하나가 실패해도 전체 작업은 계속 진행한다.

프로젝트 실패 시 저장할 정보:

- 프로젝트번호
- 실패 단계
- 실패 메시지
- 스크린샷 경로
- 재시도 횟수
- 발생 시간

## 재시도 정책

중복 파일 시스템 알림 발생 시:

1. 폴더명 변경
2. 다운로드 재시도
3. 정해진 횟수 초과 시 프로젝트 실패 처리

권장 기본값:

- 프로젝트별 다운로드 재시도: 2회
- 에이전트 창 대기 timeout: 실제 테스트 후 확정
- zip 안정화 대기: 실제 테스트 후 확정

## 재개 정책

서버 또는 작업이 중단되었다가 다시 시작되면 완료된 프로젝트는 제외한다.

재개 대상:

- pending
- running
- failed 중 사용자가 재시도를 선택한 프로젝트

재개 제외:

- completed
- skipped

## worker heartbeat

장기 작업은 별도 worker 프로세스에서 실행하므로 worker 생존 여부를 DB에 기록한다.

추천 저장값:

- worker_pid
- worker_host
- worker_heartbeat_at

heartbeat가 일정 시간 갱신되지 않으면 running 작업을 stale 상태로 보고 재개 대상으로 판단한다.

초기 기준:

```text
5분 이상 heartbeat 미갱신
```

## worker 중단 후 재개

worker가 중단되면 다음 시작 시 아래 기준으로 복구한다.

1. completed 프로젝트는 제외한다.
2. pending 프로젝트는 그대로 처리한다.
3. running 프로젝트는 중단 시점이 불명확하므로 재확인 후 재처리한다.
4. failed 프로젝트는 기본적으로 실패로 남기고, 사용자가 재시도를 요청한 경우에만 재처리한다.
5. stale 작업의 락은 worker 시작 시 복구 로직으로 정리한다.

## 사용자 구분

현재 로그인/권한 기능은 적용하지 않는다.

따라서 모든 사용자는 완료된 결과를 조회할 수 있다.
