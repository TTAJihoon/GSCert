# 화면과 API 설계

## 목적

사용자가 프로젝트를 선택해 작업을 요청하고, 브라우저를 닫아도 진행상황과 결과를 다시 조회할 수 있게 한다.

## 화면 구성 초안

실제 API 구현 전에 `13_ui_mockup_design.md` 기준으로 mock 데이터 기반 UI를 먼저 만든다.

### 프로젝트 선택 화면

기능:

- `ecmlist.db`의 `ecm_list` 테이블에서 프로젝트 목록 조회
- 프로젝트번호, 인증일자, 회사명, 제품명, 시험PL 등을 표시
- 여러 프로젝트 선택
- 현재 진행 중 작업이 있어도 작업 요청은 가능하며, 새 요청은 예약됨/대기중 상태로 표시

주요 컬럼:

- 프로젝트번호
- 인증일자
- 회사명
- 제품명
- 시험PL
- 점검결과

### 진행상황 화면

기능:

- 현재 작업 상태 표시
- 전체 프로젝트 수, 완료 수, 실패 수 표시
- 현재 처리 중 프로젝트번호 표시
- 현재 단계 메시지 표시
- 프로젝트별 상태 목록 표시

상태 메시지 예:

```text
TTA-26-00009 프로젝트 폴더 선택 중
TTA-26-00009 파일 다운로드 메뉴 실행 중
TTA-26-00009 폴더 선택 팝업 대기 중
TTA-26-00009 전송현황 완료 대기 중
TTA-26-00009 zip 검사 중
```

### 결과 조회 화면

기능:

- 완료된 작업 목록 조회
- 작업별 프로젝트 결과 조회
- 프로젝트별 파일/규칙 결과 조회
- 실패 프로젝트의 실패 단계와 메시지 조회

최소 조회 단위:

```text
작업
→ 프로젝트
→ 파일
→ 규칙
```

## API 초안

### 프로젝트 목록 조회

```text
GET /api/projects/
```

쿼리 후보:

- `project_number`
- `company`
- `product`
- `pl`
- `review`
- `cert_date`
- `q`
- `limit`
- `offset`
- `sort`

정렬:

- 기본값: `sort=cert_date_desc`
- `인증일자` 최신순, 같은 날짜는 `프로젝트번호` 내림차순
- 지원값: `cert_date_desc`, `cert_date_asc`, `project_number_desc`, `project_number_asc`

응답:

```json
{
  "success": true,
  "items": [
    {
      "project_number": "TTA-26-00009",
      "cert_date": "05/12",
      "company": "...",
      "product": "...",
      "pl": "...",
      "review": "완료",
      "inspection_date": "...",
      "selectable": false
    }
  ],
  "pagination": {
    "total": 30,
    "limit": 100,
    "offset": 0,
    "has_more": false
  },
  "sort": "cert_date_desc"
}
```

`ecmlist.db`가 없거나 `ecm_list` 테이블/필수 컬럼이 없으면 stack trace 없이 JSON 오류를 반환한다.

### 작업 요청

```text
POST /api/jobs/
```

요청:

```json
{
  "project_numbers": ["TTA-26-00009"]
}
```

성공 응답:

```json
{
  "success": true,
  "job_id": "...",
  "status": "scheduled",
  "status_label": "예약됨",
  "requested_project_count": 3,
  "available_after": "2026-05-12T11:00:00+00:00",
  "message": "작업 요청이 예약되었습니다. 시작 가능 시간이 되면 요청 순서대로 진행합니다."
}
```

진행 중 작업이 있을 때:

```json
{
  "job_id": "...",
  "status": "scheduled",
  "message": "현재 작업이 끝나면 요청 순서대로 시작합니다."
}
```

이미 예약됨/대기중/진행중인 프로젝트를 다시 요청하면 전체 요청을 실패 처리한다.

```json
{
  "success": false,
  "error_code": "active_project_conflict",
  "message": "이미 예약됨, 대기중 또는 진행중인 프로젝트가 포함되어 있습니다."
}
```

`완료` 프로젝트가 포함된 요청은 정상 UI에서는 발생할 수 없으므로 버그/우회 요청으로 보고 전체 실패 처리한다.

```json
{
  "success": false,
  "error_code": "completed_project_not_allowed",
  "message": "이미 점검 완료된 프로젝트는 작업 요청할 수 없습니다."
}
```

### 현재 작업 조회

```text
GET /api/jobs/active/
```

응답:

```json
{
  "success": true,
  "active_job": {
    "id": "...",
    "status": "running",
    "status_label": "진행중",
    "progress_percent": 40
  },
  "active_job_count": 1,
  "polling": {
    "should_poll": true,
    "recommended_interval_ms": 3000
  }
}
```

진행/예약/대기 작업이 없으면 polling을 요구하지 않는다.

```json
{
  "success": true,
  "active_job": null,
  "active_job_count": 0,
  "polling": {
    "should_poll": false,
    "recommended_interval_ms": null,
    "wake_at": null
  }
}
```

예약된 작업이 있지만 아직 시작 가능 시간이 아니면 polling을 반복하지 않고, `wake_at` 시각에 한 번 다시 조회한다.

```json
{
  "success": true,
  "active_job": {
    "id": "...",
    "status": "scheduled",
    "status_label": "예약됨",
    "available_after": "2026-05-12T11:00:00+00:00"
  },
  "polling": {
    "should_poll": false,
    "recommended_interval_ms": null,
    "wake_at": "2026-05-12T11:00:00+00:00"
  }
}
```

### 작업 목록 조회

```text
GET /api/jobs/
```

쿼리:

- `status`: `all`, `finished`, `scheduled`, `queued`, `running`, `completed`, `failed`, `canceled`
- `limit`
- `offset`

응답:

```json
{
  "success": true,
  "items": [
    {
      "id": "...",
      "status": "completed",
      "status_label": "완료",
      "requested_at": "2026-05-12T20:00:00+09:00",
      "completed_at": "2026-05-12T20:30:00+09:00",
      "requested_project_count": 3,
      "completed_project_count": 2,
      "failed_project_count": 1
    }
  ],
  "pagination": {
    "total": 1,
    "limit": 20,
    "offset": 0,
    "has_more": false
  },
  "status": "all"
}
```

결과 조회 탭은 이 API로 작업 목록을 표시하고, 선택된 작업의 프로젝트 결과는 `GET /api/jobs/{job_id}/projects/`로 조회한다.

### 작업 상세 조회

```text
GET /api/jobs/{job_id}/
```

작업 상태, 요청 프로젝트 수, 완료/실패 수, worker heartbeat 정보를 반환한다.

### 작업 프로젝트 목록 조회

```text
GET /api/jobs/{job_id}/projects/
```

작업에 포함된 프로젝트별 상태, 현재 단계, 오류 메시지, 재시도 수, zip 파일명 등을 반환한다.

### 프로젝트 검사 결과 조회

```text
GET /api/job-projects/{job_project_id}/results/
```

프로젝트별 점검 규칙 결과 표에 표시할 규칙명, 파일명, 상태, 기대값, 실제값, 메시지를 반환한다.

## 갱신 방식

초기 구현은 주기적 polling으로 충분하다.

예:

```text
진행상황 화면에서 active job이 있으면 /api/jobs/active/를 조회
```

WebSocket은 추후 필요할 때 적용한다.

초기 polling 정책:

- 진행중/대기중: 3초
- 예약됨: polling 중지, `wake_at` 시각에 브라우저 타이머로 재조회
- 진행/예약/대기 작업 없음: polling 중지

## worker 상태 표시

진행상황 화면에는 worker 상태도 함께 표시한다.

표시 후보:

- worker 실행 여부
- worker PID
- 마지막 heartbeat 시각
- 현재 active job id
- stale 여부

worker가 꺼져 있거나 heartbeat가 오래된 경우:

```text
작업 실행기가 동작하지 않습니다. 관리자에게 문의하세요.
```

## 결정된 정책

- 로그인/권한은 현재 적용하지 않는다.
- 모든 사용자는 완료 결과를 조회할 수 있다.
- 새 작업은 진행 중 작업이 있어도 생성되며, 진행 중 작업이 끝나면 요청 순서대로 처리된다.
- 진행상황은 DB 기준으로 표시한다.

## 남은 확인 필요

- 프로젝트 선택 화면에서 기본 정렬 기준
- 프로젝트 목록 검색 조건
- 결과 화면에서 Excel 다운로드가 필요한지 여부
- 실패 프로젝트만 모아보는 필터가 필요한지 여부
