# UI/API 설계

## 목적

`/download-review/` 화면에서 ECM 제출물 자동 점검 작업을 요청하고, 진행 상태와 규칙별 결과를 조회하기 위한 API 계약을 정리한다.

기준 원칙:

- 조회는 `GET`을 사용한다.
- 상태 변경은 `POST`를 사용한다.
- 모든 응답은 JSON이다.
- 사용자 화면에는 서버 절대경로와 stack trace를 표시하지 않는다.
- API 응답은 `Cache-Control: no-store`를 사용한다.
- `ecmlist.db`는 최신 요약용, `workflow.db`는 작업 이력과 상세 증거용이다.

## 화면 구조

### 프로젝트 선택 탭

역할:

- `ecmlist.db`의 `ecm_list` 프로젝트 목록 조회
- 프로젝트 검색/필터
- 점검 작업 요청
- 프로젝트별 최신 점검 결과 상세 팝업 표시

주요 버튼:

- `DB 새로고침`: `GET /api/projects/` 재조회
- `작업 요청`: `POST /api/jobs/`
- 프로젝트 행 `상세`: `GET /api/projects/{project_number}/latest-results/`

### 현재 작업 진행 상황 탭

역할:

- 현재 실행/대기/예약 작업 상태 표시
- 프로젝트별 현재 단계 표시
- 실패/보류 상세 메시지 확인

주요 API:

- `GET /api/jobs/active/`
- `GET /api/jobs/{job_id}/projects/`

진행 중 또는 대기 중이면 3초 polling을 권장한다. 예약 상태이면서 시작 가능 시간이 남아 있으면 polling을 중지하고 `wake_at` 시각에 다시 조회한다.

### 작업 조회 탭

역할:

- 과거 작업 목록 조회
- 작업별 프로젝트 결과 조회
- 예약/대기 작업 취소
- 특정 작업 기준 규칙 결과 상세 팝업 표시

주요 버튼:

- 작업 선택: `GET /api/jobs/{job_id}/projects/`
- 예약/대기 취소: `POST /api/jobs/{job_id}/cancel/`
- 프로젝트 행 `상세`: `GET /api/job-projects/{job_project_id}/results/`

## 결과 관리 기준

### workflow.db

`workflow.db`는 상세 결과 원본이다.

- 작업에 포함되어 실제 점검한 프로젝트마다 규칙 개수만큼 `DownloadReviewRuleResult`를 저장한다.
- 통과한 규칙과 실패한 규칙을 모두 저장한다.
- 같은 프로젝트를 여러 번 점검하면 작업별 이력이 모두 보존된다.
- 상세 팝업은 이 데이터를 기준으로 표시한다.

예:

```text
프로젝트 5개 × 규칙 30개 = 규칙 결과 150행
```

### ecmlist.db

`ecmlist.db`는 최신 요약 결과다.

- `점검결과`: 전체 규칙 요약
  - 전체 규칙 통과: `O`
  - 하나라도 부적합: `X`
- 산출물별 점검 컬럼: 규칙별 최신 결과
  - 통과: `O`
  - 실패: `X`
  - 미실행/대상 없음: 빈 값

산출물별 점검 컬럼은 실제 점검규칙과 1:1로 대응하므로 기존 컬럼명을 그대로 사용한다.

다운로드 실패, agent 오류, 분석 실행 실패는 `workflow.db`에 실패/보류로 남기고, `ecmlist.db`의 `O/X` 규칙 판정과 섞지 않는다.

## 상세 팝업

### 프로젝트 선택 탭의 `상세`

최신 점검 결과를 보여준다.

사용 API:

```text
GET /api/projects/{project_number}/latest-results/
```

표시 내용:

- 최신 작업 정보
- 프로젝트 정보
- 규칙별 결과 표
- 보류/실패인 경우 사용자용 오류 메시지

### 작업 조회 탭의 `상세`

선택한 작업 당시의 결과를 보여준다.

사용 API:

```text
GET /api/job-projects/{job_project_id}/results/
```

같은 프로젝트를 여러 번 점검해도 특정 작업 요청 당시의 규칙 결과만 표시한다.

### 규칙 결과 표 권장 컬럼

| 컬럼 | 설명 |
| --- | --- |
| 규칙명 | 사용자에게 보여줄 점검 항목명 |
| 결과 | `O` 또는 `X` |
| 대상 파일 | 파일명 또는 프로젝트 폴더 기준 상대 경로 |
| 기대값 | 규칙이 기대한 값 |
| 실제값 | 실제 문서/파일에서 확인한 값 |
| 메시지 | 실패 사유 또는 확인 메시지 |

서버 내부 절대경로와 stack trace는 표시하지 않는다. 필요하면 관리자 로그에서 확인한다.

## API 목록

| Method | URL | 용도 |
| --- | --- | --- |
| GET | `/api/projects/` | 프로젝트 목록 조회 |
| POST | `/api/jobs/` | 작업 요청 생성 |
| GET | `/api/jobs/active/` | 현재 작업 조회 |
| GET | `/api/jobs/` | 작업 목록 조회 |
| GET | `/api/jobs/{job_id}/` | 작업 상세 조회 |
| GET | `/api/jobs/{job_id}/projects/` | 작업 내 프로젝트 목록 조회 |
| POST | `/api/jobs/{job_id}/cancel/` | 예약/대기 작업 취소 |
| GET | `/api/job-projects/{job_project_id}/results/` | 특정 작업 프로젝트의 규칙 결과 조회 |
| GET | `/api/projects/{project_number}/latest-results/` | 프로젝트 최신 규칙 결과 조회 |

## GET /api/projects/

프로젝트 목록을 조회한다.

Query:

| 이름 | 설명 |
| --- | --- |
| `project_number` | 프로젝트번호 부분 검색 |
| `company` | 회사명 부분 검색 |
| `product` | 제품명 부분 검색 |
| `pl` | 시험PL 부분 검색 |
| `review` | 점검결과 필터 |
| `cert_date` | 인증일자 필터 |
| `q` | 프로젝트번호/회사명/제품명/시험PL 통합 검색 |
| `limit` | 조회 개수 |
| `offset` | 조회 시작 위치 |
| `sort` | `cert_date_desc`, `cert_date_asc`, `project_number_desc`, `project_number_asc` |

Response:

```json
{
  "success": true,
  "items": [
    {
      "project_number": "TTA-26-00200",
      "cert_date": "05/13",
      "company": "회사명",
      "product": "제품명",
      "pl": "시험PL",
      "review": "미점검",
      "review_raw": "",
      "inspection_date": "",
      "selectable": true,
      "active_job_id": null,
      "active_state_label": ""
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

`review_raw=O`인 프로젝트는 작업 요청 대상에서 제외한다. API는 기존 한글 값도 읽어 해석하지만, 새로 쓰는 값은 `O/X`를 기준으로 한다.

## POST /api/jobs/

점검 작업을 생성한다.

Request:

```json
{
  "project_numbers": ["TTA-26-00200"]
}
```

Response:

```json
{
  "success": true,
  "job_id": "uuid",
  "status": "queued",
  "status_label": "대기중",
  "requested_project_count": 1,
  "available_after": "2026-05-14T04:44:09.621626+00:00",
  "message": "작업 요청이 대기열에 등록되었습니다. 요청 순서대로 진행합니다."
}
```

검증:

- 프로젝트번호 형식은 `TTA-YY-NNNNN`이어야 한다.
- 없는 프로젝트가 포함되면 전체 요청을 실패 처리한다.
- 이미 예약/대기/진행 중인 프로젝트가 포함되면 전체 요청을 실패 처리한다.
- 이미 `O`로 완료된 프로젝트가 포함되면 우회 요청으로 보고 실패 처리한다.
- 작업 큐는 job 기준 최대 5개까지 허용한다.

## GET /api/jobs/active/

현재 작업을 조회한다.

Response, 작업 없음:

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

Response, 진행/대기:

```json
{
  "success": true,
  "active_job": {
    "id": "uuid",
    "status": "running",
    "status_label": "진행중",
    "progress_percent": 40,
    "progress_message": "ECM 자동화 진행 중"
  },
  "active_job_count": 1,
  "polling": {
    "should_poll": true,
    "recommended_interval_ms": 3000,
    "wake_at": null
  }
}
```

Response, 예약:

```json
{
  "success": true,
  "active_job": {
    "id": "uuid",
    "status": "scheduled",
    "status_label": "예약중",
    "available_after": "2026-05-14T11:00:00+00:00"
  },
  "polling": {
    "should_poll": false,
    "recommended_interval_ms": null,
    "wake_at": "2026-05-14T11:00:00+00:00"
  }
}
```

## GET /api/jobs/

작업 목록을 조회한다.

Query:

| 이름 | 설명 |
| --- | --- |
| `status` | `all`, `finished`, `scheduled`, `queued`, `running`, `completed`, `failed`, `canceled` |
| `limit` | 조회 개수 |
| `offset` | 조회 시작 위치 |

Response:

```json
{
  "success": true,
  "items": [
    {
      "id": "uuid",
      "status": "completed",
      "status_label": "완료",
      "requested_project_count": 3,
      "completed_project_count": 2,
      "failed_project_count": 1,
      "progress_percent": 100
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

## GET /api/jobs/{job_id}/

작업 상세를 조회한다.

반환 정보:

- 작업 상태
- 요청/시작/완료/취소 시각
- 요청 프로젝트 수
- 완료/실패 프로젝트 수
- progress message
- worker pid/host/heartbeat
- polling hint

## GET /api/jobs/{job_id}/projects/

작업에 포함된 프로젝트 목록과 상태를 조회한다.

Response item:

```json
{
  "id": "job_project_uuid",
  "job_id": "job_uuid",
  "project_number": "TTA-26-00200",
  "cert_date": "05/13",
  "company": "회사명",
  "product": "제품명",
  "pl": "시험PL",
  "status": "downloaded",
  "status_label": "다운로드완료",
  "review_status": "unreviewed",
  "review_status_label": "미점검",
  "current_step": "다운로드 완료 (3개 파일)",
  "error_message": "",
  "error_detail": "",
  "retry_count": 0,
  "zip_file_name": "",
  "download_dir": "TTA-26-00200_2",
  "started_at": "2026-05-14T13:44:00+09:00",
  "completed_at": "2026-05-14T13:48:00+09:00"
}
```

`download_dir`는 서버 절대경로가 아니라 프로젝트 폴더 기준 표시 경로만 반환한다.

## POST /api/jobs/{job_id}/cancel/

예약/대기 작업을 취소한다.

허용 상태:

- `scheduled`
- `queued`

진행 중인 작업은 취소하지 않는다.

Response:

```json
{
  "success": true,
  "job": {},
  "message": "예약된 작업을 취소했습니다."
}
```

## GET /api/job-projects/{job_project_id}/results/

특정 작업 프로젝트의 규칙 결과를 조회한다.

이 API는 조회 전용이다. 규칙 결과는 worker가 생성한 실행 증거이므로 웹 화면에서 직접 수정하지 않는다.

Response:

```json
{
  "success": true,
  "job": {},
  "project": {},
  "items": [
    {
      "id": "rule_result_uuid",
      "job_project_id": "job_project_uuid",
      "rule_id": "rule_uuid",
      "rule_code": "contract_file",
      "rule_name": "계약서",
      "sequence": 1,
      "file_path": "TTA-26-00200/계약서.pdf",
      "file_name": "계약서.pdf",
      "status": "pass",
      "status_label": "정상",
      "expected": "프로젝트번호 포함",
      "actual": "TTA-26-00200",
      "message": "계약서 파일명이 기준을 만족합니다.",
      "raw_detail": {},
      "created_at": "2026-05-14T13:48:00+09:00"
    }
  ]
}
```

규칙 결과가 30개라면 통과/실패와 관계없이 30개 item을 반환한다.

## GET /api/projects/{project_number}/latest-results/

프로젝트의 최신 규칙 결과를 조회한다.

이 API는 조회 전용이다. 프로젝트 최신 결과는 특정 작업의 규칙 결과를 기준으로 표시하며, 웹 화면에서 직접 수정하지 않는다.

기준:

- active job은 제외한다.
- canceled job은 제외한다.
- 가장 최근 완료/실패/보류 이력을 사용한다.

프로젝트 선택 탭의 `상세` 버튼에서 사용한다.

## 오류 응답

공통 형식:

```json
{
  "success": false,
  "error_code": "invalid_job_request",
  "message": "사용자에게 보여줄 메시지",
  "details": {}
}
```

권장 status code:

| 상황 | HTTP |
| --- | --- |
| 잘못된 요청 | 400 |
| 찾을 수 없음 | 404 |
| 중복/큐 초과/취소 불가 | 409 |
| 기준 DB 없음 | 503 |
| 서버 내부 오류 | 500 |

## 앞으로 구현할 API 보강

다음 구현에서 정리할 항목:

- 규칙 목록 API가 필요한지 여부
- 규칙 결과 저장 후 cleanup 상태 표시
- 분석 완료 후 다운로드 파일 삭제 결과 표시
- `ecmlist.db` write-back 실패 시 사용자 메시지와 관리자 로그 분리
- 작업 결과 Excel 내보내기 필요 여부
- 수동 보정/재검토가 필요해질 경우, 조회 API와 분리된 별도 수정 API를 새로 설계한다.
