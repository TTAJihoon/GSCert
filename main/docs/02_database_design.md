# DB 설계

## 프로젝트 기준 DB

프로젝트 목록은 별도 SQLite 파일에서 관리한다.

- 위치:
  - 상암: `main/data/ecmlist.db`
  - 영남: `main/data/ecmlist2.db`
- 테이블명: `ecm_list`
- 컬럼 타입: 모두 문자열
- `WD`는 Google Sheet F열에서 가져온다.

## ecm_list 테이블 컬럼

- 번호
- 인증일자
- 프로젝트번호
- 회사명
- 제품명
- 시험PL
- WD
- 점검결과
- 계약서
- 합의서(PDF)
- 수수료산정표
- 시험환경구성도
- 품질특성별제품정보기재사항
- 기능리스트
- 시험계획서(PDF)
- 점검표(PDF)
- 최초/최종형상RawData
- 테스트케이스
- 결함리포트
- 1차/2차/성능/보안RawData
- 시험성적서(PDF)
- 시험기록서
- 품질평가보고서
- 품질검사표
- SW저작권확인서
- 홍보이미지

## ecmlist.db 갱신 정책

- `번호`, `인증일자`, `프로젝트번호`, `회사명`, `제품명`, `시험PL`, `WD`는 기준정보로 취급해 자동 갱신하지 않는다.
- 자동 점검 결과는 `점검결과`부터 `홍보이미지`까지의 점검 컬럼만 갱신한다.
- `점검결과` 값은 전체 규칙 판정 요약으로 `O` 또는 `X`를 사용한다.
- 모든 규칙이 통과하면 `점검결과=O`, 하나라도 부적합이면 `점검결과=X`로 갱신한다.
- 산출물별 점검 컬럼은 실제 점검규칙과 1:1로 대응하므로 기존 컬럼명을 그대로 사용한다.
- 산출물별 점검 컬럼 값은 해당 규칙의 최신 통과 여부로 `O` 또는 `X`를 사용한다.
- 미실행/대상 없음 기본값은 빈 값으로 둔다.
- 다운로드/agent/분석 실행 실패는 workflow DB에 실패/보류로 남기고, `ecmlist.db`의 규칙 판정 `O/X`와 섞지 않는다.

현재 샘플 DB 상태:

- `main/data/ecmlist.db`와 `main/data/ecmlist2.db`에는 `WD` 컬럼이 추가되어 있다.
- `main/utils/ecmList/sync_sheets.py`는 신규 프로젝트 추가 시 Google Sheet F열 값을 `WD`에 저장한다.

## 실행 이력 DB

작업 상태, 락, 다운로드 이력, 검사 결과는 Django 기본 DB와 분리된 실행 이력 DB로 관리하는 방향을 우선 검토한다.

추천 파일:

- `main/data/workflow.db`

확정 방향:

- `ecmlist.db`: 프로젝트 기준 데이터
- `ecmlist2.db`: 영남 프로젝트 기준 데이터
- `workflow.db`: 작업, 락, 다운로드, 검사 결과 데이터
- Django 인증/관리 기본 테이블은 기존 `db.sqlite3` 사용 가능

운영 중 기준 데이터를 갱신하더라도 작업 이력과 검사 결과가 영향을 덜 받도록 DB를 분리한다.

## 주요 테이블 초안

### automation_job

하나의 사용자 요청 단위다.

- id
- status
- requested_at
- started_at
- completed_at
- progress_message
- requested_project_count
- completed_project_count
- failed_project_count

상세 컬럼 초안:

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| id | TEXT | 작업 ID, UUID 문자열 |
| status | TEXT | pending, running, completed, failed, canceled |
| requested_at | TEXT | 요청 시각 |
| started_at | TEXT | 시작 시각 |
| completed_at | TEXT | 완료 시각 |
| progress_message | TEXT | 현재 진행 메시지 |
| requested_project_count | TEXT | 요청 프로젝트 수 |
| completed_project_count | TEXT | 완료 프로젝트 수 |
| failed_project_count | TEXT | 실패 프로젝트 수 |
| selected_projects_json | TEXT | 사용자가 선택한 프로젝트번호 목록 JSON |
| last_error_message | TEXT | 작업 단위 마지막 오류 |

### automation_job_project

작업에 포함된 프로젝트별 처리 단위다.

- id
- job_id
- 프로젝트번호
- status
- download_dir
- zip_path
- error_message
- started_at
- completed_at
- retry_count

상세 컬럼 초안:

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| id | TEXT | 프로젝트 처리 ID |
| job_id | TEXT | automation_job.id |
| project_number | TEXT | 예: TTA-26-00009 |
| ecm_row_json | TEXT | 처리 당시 ecm 행 데이터 스냅샷 |
| status | TEXT | pending, running, downloaded, inspecting, completed, failed, skipped |
| download_dir | TEXT | 프로젝트별 다운로드 폴더 |
| zip_path | TEXT | (미사용, 개별 파일 다운로드 방식으로 변경됨. download_dir 참조) |
| current_step | TEXT | 현재 단계 |
| error_message | TEXT | 실패 메시지 |
| retry_count | TEXT | 다운로드 재시도 횟수 |
| started_at | TEXT | 시작 시각 |
| completed_at | TEXT | 완료 시각 |

`ecm_row_json`을 저장하는 이유:

- 기준 DB가 나중에 변경되어도 당시 검사 기준을 추적할 수 있다.
- 결과 화면에서 회사명, 제품명 등 프로젝트 정보를 빠르게 표시할 수 있다.

### automation_lock

동시에 하나의 작업만 실행되도록 제어한다.

- id
- locked
- job_id
- locked_at

락 정책:

- row는 1개만 사용한다.
- 새 작업 생성 시 트랜잭션으로 이 row를 잠근다.
- locked가 true이고 연결된 작업이 running 또는 pending이면 새 작업을 거절한다.
- 서버 재시작 후 locked가 true인데 실제 실행기가 없으면 복구 정책에 따라 재개 대상으로 표시한다.

### inspection_rule

파일 검사 규칙을 저장한다.

- id
- name
- target_file_type
- rule_type
- config_json
- enabled
- version

상세 컬럼 초안:

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| id | TEXT | 규칙 ID |
| name | TEXT | 규칙명 |
| target_file_pattern | TEXT | 대상 파일명 패턴 |
| target_file_type | TEXT | zip, docx, xlsx, pdf, any |
| rule_type | TEXT | 검사 유형 |
| config_json | TEXT | 검사 상세 조건 |
| severity | TEXT | error, warning, info |
| enabled | TEXT | Y/N |
| version | TEXT | 규칙 버전 |

### inspection_result

프로젝트별, 파일별, 규칙별 검사 결과 최소 단위다.

- id
- job_project_id
- rule_id
- file_path
- status
- expected
- actual
- message

상세 컬럼 초안:

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| id | TEXT | 결과 ID |
| job_project_id | TEXT | automation_job_project.id |
| rule_id | TEXT | inspection_rule.id |
| file_path | TEXT | zip 내부 파일 경로 |
| status | TEXT | pass, fail, warning, error |
| expected | TEXT | 기대값 |
| actual | TEXT | 실제값 |
| message | TEXT | 화면 표시 메시지 |
| raw_detail_json | TEXT | 추가 디버그 정보 |

저장 정책:

- 작업에 포함되어 실제 점검한 프로젝트마다 규칙 개수만큼 결과 행을 저장한다.
- 통과한 규칙과 실패한 규칙을 모두 저장한다.
- 예: 프로젝트 5개, 규칙 30개를 점검하면 `inspection_result`에는 150행을 저장한다.
- `ecmlist.db` 전체 프로젝트에 대해 미리 결과 행을 만들지는 않는다.
- job/project에는 `center_code`를 저장한다. 같은 프로젝트번호가 센터별 DB에 모두 있어도 선택한 센터 기준으로 조회, 중복 검사, write-back을 처리한다.

## 별도 테이블 후보

### downloaded_file

zip 자체와 내부 파일 목록을 추적하기 위한 테이블이다.

초기 구현에서는 `inspection_result.raw_detail_json`으로 대체할 수 있다. 파일 단위 조회 UI가 복잡해지면 별도 테이블로 분리한다.

컬럼 후보:

- id
- job_project_id
- zip_path
- inner_path
- file_name
- extension
- file_size
- modified_at

## 상태 전이

작업 상태:

```text
pending
→ running
→ completed
```

실패 또는 취소:

```text
running → failed
running → canceled
```

프로젝트 상태:

```text
pending
→ running
→ downloaded
→ inspecting
→ completed
```

프로젝트 실패:

```text
running/downloaded/inspecting → failed
```

## 설계 원칙

- 기준 데이터와 실행 이력은 분리한다.
- 완료된 프로젝트는 재시작 시 다시 처리하지 않는다.
- 검사 결과는 UI에서 프로젝트별, 파일별, 규칙별로 조회할 수 있어야 한다.

## 프로젝트번호 형식

프로젝트번호는 아래 형식의 문자열이다.

```text
TTA-26-00009
```

웹페이지1의 프로젝트 폴더명에는 이 프로젝트번호가 포함되어 있으므로, 자동화는 `프로젝트번호` 컬럼 값을 기준으로 폴더를 찾는다.
