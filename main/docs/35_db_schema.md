# GSCert DB 스키마 정리

이 문서는 GSCert의 데이터베이스/테이블 구조를 한곳에 정리한 것이다. 정의 원본은
`main/models.py`, DB 분리 규칙은 `main/db_routers.py`, 접속 설정은 `myproject/settings.py`다.

## 1. 데이터베이스(3개) 구성

Django `DATABASES` alias 3개로 나뉜다. 어떤 모델이 어느 DB로 가는지는 `DATABASE_ROUTERS`가 결정한다.

| alias | 엔진 | 위치 | 용도 |
|---|---|---|---|
| `default` | SQLite | `db.sqlite3` (프로젝트 루트) | 기타(레거시 `Job` 등). 세션/auth 등 Django 기본 테이블도 여기. |
| `workflow` | SQLite | `main/data/workflow.db` (**서버 로컬**) | 다운로드/점검 **실행 상태**(잡·프로젝트·결과·로그·락). 서버마다 로컬. |
| `reference` | **PostgreSQL** | `gscert_reference` (주 서버, env로 접속) | **공유 기준 데이터**(점검규칙·프로젝트·PL 매핑·인증이력). 여러 서버가 공유. |

- 접속 정보(`reference`): `REFERENCE_PG_NAME/USER/PASSWORD/HOST/PORT` 환경변수.
- 라우팅 규칙(`settings.py`):
  - `WORKFLOW_MODEL_NAMES` → `workflow` alias
  - `REFERENCE_MODEL_NAMES` → `reference` alias
  - 그 외 → `default`
- `DOWNLOAD_REVIEW_PROJECT_SOURCE = 'postgres'` → 프로젝트 조회는 `reference`의 `reference_project` 우선.

## 2. 테이블 요약

| 테이블 | 모델 | DB | 용도 |
|---|---|---|---|
| `reference_center_pl` | `ReferenceCenterPl` | reference | **센터별 PL 이름 매핑** (PL 이름 → 센터) |
| `reference_project` | `ReferenceProject` | reference | 프로젝트 기준정보(센터/회사/제품/PL/일정 등). 센터 해석의 소스 |
| `sw_data` | `SwData` | reference | GS 인증 획득 이력(유사제품/이력 조회용) |
| `inspection_rule` | `DownloadReviewRule` | reference | 점검규칙 정의(두 서버 공유, admin 수정) |
| `automation_job` | `DownloadReviewJob` | workflow | 다운로드 검토 **잡** |
| `automation_job_project` | `DownloadReviewProject` | workflow | 잡에 속한 **프로젝트별** 처리 상태 |
| `inspection_result` | `DownloadReviewRuleResult` | workflow | 프로젝트별 **규칙 점검 결과** |
| `automation_log` | `DownloadReviewLog` | workflow | 잡/프로젝트 처리 로그 |
| `automation_lock` | `DownloadReviewLock` | workflow | 단일 워커 동시성 락(단일 행) |
| `main_job` | `Job` | default | 레거시 잡(상태/최종 링크) |

> ⚠️ 크로스-DB 관계 불가: `inspection_result.rule_code`는 `inspection_rule`(다른 DB)로의 FK가 아니라
> **비정규화된 코드 문자열**이다. Django는 서로 다른 DB 간 FK를 지원하지 않는다.

---

## 3. reference DB (PostgreSQL, 공유 기준 데이터)

### 3.1 `reference_center_pl` — 센터별 PL 이름 매핑
PL(프로젝트 리더) 이름을 센터에 매핑한다. `sync_reference_projects_from_sheet`가 시트에서 채운다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | PK(auto) | |
| `center_code` | varchar(20), index | `bundang`/`sangam`/`yeongnam` |
| `center_label` | varchar(20) | 분당/상암/영남 |
| `name` | varchar(50), **unique** | **PL 이름(매핑 키)** |
| `display_order` | smallint | 정렬 순서 |
| `created_at`/`updated_at` | datetime | |

인덱스: `(center_code, name)`

### 3.2 `reference_project` — 프로젝트 기준정보
프로젝트번호 단위 기준정보. **전체 다운로드(#2)의 센터 해석은 이 표의 `center_code`를 사용**한다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | PK(auto) | |
| `project_number` | varchar(32), **unique**, index | 시험번호(예: `GS-A-23-0336`, `TTA-26-00009`) |
| `center_code` | varchar(20), index | 센터 코드 |
| `center_label` | varchar(20) | 센터 표시명 |
| `cert_date` | varchar(20) | 인증일(문자열) |
| `cert_committee_date` | date, index | 인증위 날짜 |
| `company` / `product` | text | 회사명/제품명 |
| `pl` | text | PL 이름 |
| `primary_tester` | varchar(50), index | 주 시험원 |
| `wd` | text | WD |
| `request_date`/`contract_date`/`start_date`/`expected_end_date` | text | 일정 |
| `review_result` | varchar(20) | 심의 결과 |
| `inspection_date` | text | |
| `artifact_results_json` | jsonb | 산출물 점검 결과 캐시 |
| `raw_company_product` | text | 원본 회사/제품 문자열 |
| `source_spreadsheet_id`/`source_gid`/`source_row_number`/`source_payload_json` | | 시트 출처 추적 |
| `created_at`/`updated_at` | datetime | |

인덱스: `(center_code, cert_committee_date)`, `(center_code, project_number)`, `(primary_tester)`

### 3.3 `sw_data` — GS 인증 획득 이력
유사제품 검색/이력 조회용 참조 데이터(구 `reference.db` `sw_data`).

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `serial_number` | int, **PK** | 일련번호 |
| `cert_number` | text | 인증번호 |
| `cert_date` | text | 인증일 |
| `company`/`product` | text | 회사/제품 |
| `grade` | text | 등급 |
| `test_number` | text | 시험번호 |
| `sw_category`/`product_desc`/`total_wd`/`renewal`/`notes`/`date_range`/`test_lab`/`start_date`/`end_date` | text | 부가 정보 |

### 3.4 `inspection_rule` — 점검규칙 정의
점검규칙을 주 서버에 단일 저장 → 194/241 공유, Django admin에서 수정. 상세: `27_rule_db_edit_quick_guide.md`.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `code` | varchar(80), **unique** | 규칙 코드 |
| `name` | varchar(255) | 규칙명 |
| `target_file_pattern` | varchar(255) | 대상 파일 매칭 패턴 |
| `target_file_type` | varchar(30) | 기본 `any` |
| `rule_type` | varchar(80) | 규칙 유형 |
| `config_json` | jsonb | 규칙 설정(엔진 실행 파라미터) |
| `severity` | varchar(20) | `error`/`warning`/`info` |
| `enabled` | bool, index | 활성 여부 |
| `version` | varchar(40) | 규칙 버전 |
| `sort_order` | smallint | 정렬 |
| `created_at`/`updated_at` | datetime | |

---

## 4. workflow DB (SQLite, 서버 로컬 실행 상태)

### 4.1 `automation_job` — 다운로드 검토 잡 (`DownloadReviewJob`)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `center_code` | varchar(20), index | 잡 센터 |
| `status` | varchar(20), index | `scheduled`/`queued`/`running`/`completed`/`failed`/`canceled` |
| `requested_at`/`queued_at`/`started_at`/`completed_at`/`canceled_at`/`available_after` | datetime | 상태 시각 |
| `progress_message` | varchar(500) | 진행 메시지 |
| `requested_project_count`/`completed_project_count`/`failed_project_count` | int | 집계 |
| `selected_projects_json` | json | 선택 프로젝트 목록 |
| `requested_ip` | inet | 요청 IP |
| `last_error_message` | text | |
| `worker_pid`/`worker_host`/`worker_heartbeat_at` | | 워커 추적 |
| `created_at`/`updated_at` | datetime | |

### 4.2 `automation_job_project` — 프로젝트별 처리 (`DownloadReviewProject`)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `job_id` | FK → automation_job | |
| `center_code` | varchar(20), index | |
| `project_number` | varchar(32), index | 시험번호 |
| `ecm_row_json` | json | 원본 프로젝트 dict(회사/제품/인증일 등) |
| `status` | varchar(20), index | `queued`/`running`/`downloaded`/`inspecting`/`completed`/`failed`/`skipped` |
| `review_status` | varchar(20), index | `unreviewed`/`completed`/`needs_fix`/`held` |
| `download_dir`/`zip_path`/`zip_file_name`/`zip_deleted_at` | | 산출물 경로 |
| `current_step`/`error_message`/`error_detail`/`retry_count` | | 진행/오류 |
| `started_at`/`completed_at`/`created_at`/`updated_at` | datetime | |

제약: `(job, project_number)` unique.

### 4.3 `inspection_result` — 규칙 점검 결과 (`DownloadReviewRuleResult`)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `job_project_id` | FK → automation_job_project | |
| `rule_code`/`rule_name` | | 규칙 식별(비정규화, cross-DB라 FK 아님) |
| `sequence` | smallint | |
| `file_path`/`file_name` | | 대상 파일 |
| `status` | varchar(20), index | `pass`/`fail`/`warning`/`error` |
| `expected`/`actual`/`message` | text | 기대/실제/메시지 |
| `raw_detail_json` | json | |
| `created_at` | datetime | |

### 4.4 `automation_log` — 처리 로그 (`DownloadReviewLog`)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | PK(auto) | |
| `job_id`/`job_project_id` | FK(nullable) | |
| `level` | varchar(20), index | `debug`/`info`/`warning`/`error` |
| `event_code` | varchar(80) | |
| `message` | text | |
| `detail_json` | json | |
| `admin_only` | bool | 관리자 전용 여부 |
| `created_at` | datetime, index | |

### 4.5 `automation_lock` — 워커 동시성 락 (`DownloadReviewLock`)
단일 행(id=1)으로 워커 동시 실행을 제어.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | smallint, PK(기본 1) | |
| `locked` | bool | 잠금 여부 |
| `owner` | varchar(80) | 점유자 |
| `job_id` | FK(nullable) → automation_job | |
| `locked_at`/`heartbeat_at`/`updated_at` | datetime | |
| `note` | varchar(255) | |

---

## 5. default DB (SQLite)

### 5.1 `main_job` — 레거시 잡 (`Job`)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `status` | varchar(20) | `PENDING`/`RUNNING`/`DONE`/`ERROR` |
| `final_link` | url | |
| `error` | text | |
| `created_at`/`updated_at` | datetime | |

Django 기본 테이블(auth/sessions/admin 등)도 `default` DB에 있다.

---

## 6. 참고
- 점검규칙 수정 절차: `main/docs/27_rule_db_edit_quick_guide.md`
- 규칙 공유 아키텍처: `main/docs/26_rulebase_shared_architecture.md`
- PostgreSQL/API 조회 매뉴얼: `main/docs/24_postgresql_api_access_manual.md`
- 시트 → reference_project 적재: `main/docs/28_reference_project_sheet_sync.md`
