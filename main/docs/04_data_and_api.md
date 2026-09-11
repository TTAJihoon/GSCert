# 데이터와 API

DB 컬럼 정의, API 계약, 기준정보 동기화의 단일 기준 문서다. 세 부분으로 구성된다.

1. **API 조회** — PostgreSQL에 직접 붙지 않고 API로 기준정보를 조회하는 방법.
2. **DB 스키마** — `default`/`workflow`/`reference` 3개 DB와 테이블 구조.
3. **기준정보 동기화** — `reference_project`를 채우는 두 경로와 파싱 규칙.

## 빠른 사용 가이드

PostgreSQL에 직접 접속해서 `SELECT` 쿼리를 실행하는 대신, 아래 API 주소를 호출해서 같은 목적의 데이터를 조회한다.

기본 서버 주소 예시:

```text
http://210.96.71.194:8000
```

194 서버가 download-review와 로컬 앱 API의 기준 진입점이다. 실제 운영 포트나 HTTPS 배포가 다르면 서버 배포 주소에 맞춰 바꾼다.

| 목적 | API 주소 | 주요 파라미터 | 호출 예시 |
| --- | --- | --- | --- |
| 서버 연결 확인 | `GET /api/local-review/health/` | 없음 | `Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/health/" -Method Get` |
| 프로젝트 1건 기준정보 조회 | `GET /api/local-review/projects/{project_number}/metadata/` | `center`: `bundang`, `sangam`, `yeongnam` | `Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/projects/TTA-26-00727/metadata/?center=sangam" -Method Get` |
| 프로젝트 목록 조회 | `GET /api/projects/` | `center`, `limit`, `offset`, `sort` | `Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&limit=100&offset=0&sort=cert_date_desc" -Method Get` |
| 프로젝트 검색 | `GET /api/projects/` | `q`, `project_number`, `company`, `product`, `pl` | `Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&q=TTA-26-00727" -Method Get` |
| 점검결과별 조회 | `GET /api/projects/` | `review`: `완료`, `실패`, `보류`, `미점검` | `Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&review=실패" -Method Get` |

가장 자주 쓰는 조회는 프로젝트 1건 기준정보 조회다.

```powershell
$response = Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/projects/TTA-26-00727/metadata/?center=sangam" -Method Get
$response.project
```

응답에서 자주 쓰는 필드는 다음과 같다.

| 필요한 값 | 응답 필드 |
| --- | --- |
| 프로젝트 번호 | `project.project_number` |
| 회사명 | `project.company_name` |
| 제품명 | `project.product_name` |
| 시험 PL | `project.pl_name` |
| WD | `project.wd_name` |
| 신청일 | `project.request_date` |
| 계약일 | `project.contract_date` |
| 인증일 | `project.cert_date` |
| 점검결과 | `project.review` |

목록 조회 결과는 `items`에 들어 있다.

```powershell
$response = Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&limit=100" -Method Get
$response.items
```

## 파라미터 요약

`/api/projects/`에서 사용할 수 있는 주요 파라미터는 다음과 같다.

| 파라미터 | 설명 | 예시 |
| --- | --- | --- |
| `center` | 센터 구분 | `bundang`, `sangam`, `yeongnam` |
| `project_number` | 프로젝트 번호 검색 | `TTA-26-00727` |
| `company` | 회사명 일부 검색 | `테스트회사` |
| `product` | 제품명 일부 검색 | `제품명` |
| `pl` | PL명 검색 | `홍길동` |
| `q` | 프로젝트번호/회사명/제품명/PL 통합 검색 | `TTA-26` |
| `review` | 점검결과 필터 | `완료`, `실패`, `보류`, `미점검` |
| `cert_date` | 인증일자 필터 | `6/18` |
| `limit` | 한 번에 가져올 개수 | `100` |
| `offset` | 건너뛸 개수 | `0`, `100` |
| `sort` | 정렬 | `cert_date_desc`, `cert_date_asc`, `project_number_desc`, `project_number_asc` |

초기 사용자는 보통 아래 3개만 알면 된다.

```text
center=sangam
project_number=TTA-26-00727
q=검색어
```

## 현재 결론

현재 상태에서 외부 PC가 PostgreSQL에 직접 접속해서 데이터를 조회하는 구조는 아니다.

권장 구조는 다음과 같다.

```text
외부 Windows PC
  -> Django API 호출
  -> Django 서버가 PostgreSQL 조회
  -> JSON 응답 반환
```

PostgreSQL `5432` 포트를 외부에 직접 열지 않는 이유는 다음과 같다.

- 데스크톱 앱에 DB 계정과 비밀번호를 넣지 않아도 된다.
- DB 스키마가 바뀌어도 앱을 매번 재배포하지 않아도 된다.
- 외부 접속 보안 범위를 Django API로 좁힐 수 있다.
- 조회 권한, 인증, 로그, 오류 메시지를 서버에서 통제할 수 있다.

따라서 “외부에서 데이터 조회”는 PostgreSQL 직접 접속이 아니라 서버 API 조회로 진행한다.

## SELECT 쿼리처럼 API를 사용하는 방식

API 방식은 SQL을 없애는 것이 아니라, 외부 사용자가 직접 SQL을 작성하지 않도록 서버가 정해진 조회 API로 감싸는 방식이다.

사용자는 다음처럼 생각하면 된다.

```text
SELECT 문
  -> API URL

WHERE 조건
  -> URL path 또는 query string

SELECT 컬럼
  -> JSON 응답 필드

ORDER BY / LIMIT / OFFSET
  -> sort / limit / offset query string
```

즉, 외부 PC나 Windows 앱에서는 `SELECT * FROM ...`를 직접 실행하지 않고, `GET /api/...`를 호출한다. 실제 DB 조회는 Django 서버 내부에서 수행한다.

### 기본 매핑

| SQL에서 하던 일 | API에서 하는 방법 |
| --- | --- |
| 테이블 선택 | 정해진 API endpoint 선택 |
| `WHERE project_number = 'TTA-26-00727'` | URL path에 프로젝트 번호 입력 |
| `WHERE center = 'sangam'` | `?center=sangam` query string 입력 |
| 필요한 컬럼 선택 | JSON 응답에서 필요한 필드만 사용 |
| `LIMIT 100` | `?limit=100` query string 입력 |
| `OFFSET 100` | `?offset=100` query string 입력 |
| `ORDER BY 인증일자 DESC` | `?sort=cert_date_desc` query string 입력 |

## SQL과 API 호출 예시

### 1. 서버 연결 확인

SQL로 표현하면 다음과 비슷한 확인 작업이다.

```sql
SELECT 1;
```

API로는 다음처럼 호출한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/health/" -Method Get
```

정상 응답 예시는 다음과 같다.

```json
{
  "success": true,
  "ok": true,
  "server_time": "2026-06-18T..."
}
```

### 2. 프로젝트 번호로 1건 조회

SQL로 직접 조회한다면 다음과 같은 느낌이다.

```sql
SELECT
    프로젝트번호,
    회사명,
    제품명,
    시험PL,
    WD,
    신청일,
    계약일,
    인증일자,
    점검결과
FROM ecm_list
WHERE 프로젝트번호 = 'TTA-26-00727'
  AND center = 'sangam';
```

API로는 다음처럼 호출한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/projects/TTA-26-00727/metadata/?center=sangam" -Method Get
```

응답에서 SQL 컬럼에 대응되는 JSON 필드는 다음과 같다.

| SQL 컬럼 | API 응답 필드 |
| --- | --- |
| `프로젝트번호` | `project.project_number` |
| `회사명` | `project.company_name` |
| `제품명` | `project.product_name` |
| `시험PL` | `project.pl_name` |
| `WD` | `project.wd_name` |
| `신청일` | `project.request_date` |
| `계약일` | `project.contract_date` |
| `인증일자` | `project.cert_date` |
| `점검결과` | `project.review` |

PowerShell에서 필요한 값만 꺼내려면 다음처럼 사용할 수 있다.

```powershell
$response = Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/projects/TTA-26-00727/metadata/?center=sangam" -Method Get
$response.project.project_number
$response.project.company_name
$response.project.product_name
```

### 3. 프로젝트 목록 조회

기존 프로젝트 목록 API는 SQL의 `SELECT ... FROM ecm_list WHERE ... ORDER BY ... LIMIT ...` 역할을 한다.

SQL로 표현하면 다음과 비슷하다.

```sql
SELECT
    프로젝트번호,
    회사명,
    제품명,
    시험PL,
    WD,
    인증일자,
    점검결과
FROM ecm_list
WHERE center = 'sangam'
ORDER BY 인증일자 DESC
LIMIT 100
OFFSET 0;
```

API로는 다음처럼 호출한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&limit=100&offset=0&sort=cert_date_desc" -Method Get
```

응답의 `items` 배열이 SQL 결과 rows에 해당한다.

```powershell
$response = Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&limit=100&offset=0&sort=cert_date_desc" -Method Get
$response.items | Select-Object project_number, company, product, pl, wd, cert_date, review
```

### 4. 조건 검색

회사명, 제품명, 프로젝트 번호 일부로 검색하는 쿼리는 API query string으로 대체한다.

SQL 예시는 다음과 같다.

```sql
SELECT *
FROM ecm_list
WHERE center = 'sangam'
  AND 회사명 LIKE '%테스트회사%'
ORDER BY 인증일자 DESC;
```

API 예시는 다음과 같다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&company=테스트회사&sort=cert_date_desc" -Method Get
```

제품명 검색은 다음과 같다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&product=제품명일부" -Method Get
```

통합 검색은 `q` 파라미터를 사용한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&q=TTA-26-00727" -Method Get
```

### 5. 점검결과 기준 조회

SQL로 표현하면 다음과 같다.

```sql
SELECT *
FROM ecm_list
WHERE center = 'sangam'
  AND 점검결과 = '실패';
```

API로는 다음처럼 호출한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&review=실패" -Method Get
```

완료 항목을 조회하려면 다음처럼 호출한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/projects/?center=sangam&review=완료" -Method Get
```

### 6. Python에서 SELECT 대신 API 사용

Python에서 DB에 직접 접속했다면 다음처럼 작성했을 수 있다.

```python
cursor.execute(
    "SELECT 프로젝트번호, 회사명, 제품명 FROM ecm_list WHERE 프로젝트번호 = %s",
    ["TTA-26-00727"],
)
row = cursor.fetchone()
```

API 방식에서는 다음처럼 작성한다.

```python
import requests

base_url = "http://210.96.71.194:8000"
project_number = "TTA-26-00727"
response = requests.get(
    f"{base_url}/api/local-review/projects/{project_number}/metadata/",
    params={"center": "sangam"},
    timeout=10,
)
response.raise_for_status()
project = response.json()["project"]

print(project["project_number"])
print(project["company_name"])
print(project["product_name"])
```

이 방식에서는 DB 접속 정보가 Python 코드나 Windows 앱에 들어가지 않는다.

## API 사용 시 주의사항

- 조회는 `GET`을 사용한다.
- 조회 조건은 URL path 또는 query string으로 전달한다.
- 응답은 JSON으로 받는다.
- SQL 컬럼명 대신 API 응답 필드명을 사용한다.
- API가 제공하지 않는 조건이나 컬럼이 필요하면 DB를 직접 열기보다 API 필드를 추가한다.
- 외부 사용자에게 서버 파일 경로, stack trace, DB 내부 오류 메시지를 노출하지 않는다.
- 대량 조회가 필요하면 `limit`, `offset`을 사용해 페이지 단위로 조회한다.

## 현재 구현된 상태

운영 기준에서 프로젝트 기준정보, PL 매핑, 인증 이력, 점검규칙, 수동 적합 메모는 PostgreSQL `reference` DB를 사용한다. 작업 상태, 점검 결과 원본, 유사 분석 작업은 서버 로컬 `workflow.db`에 남긴다. 상세 구조는 `04_data_and_api.md`가 기준이다.

현재 구현된 서버 API는 다음과 같다.

| API | 상태 | 설명 |
| --- | --- | --- |
| `GET /api/local-review/health/` | 구현 완료 | 서버 연결 상태 확인 |
| `GET /api/local-review/projects/<project_number>/metadata/?center=sangam` | 구현 완료 | 프로젝트 기준정보 조회 |
| `GET /api/projects/?center=sangam` | 구현 완료 | download-review 프로젝트 목록/검색/필터 조회 |
| `GET /api/pl-assignments/` | 구현 완료 | 센터별 PL과 미배정 PL 목록 조회 |
| `POST /api/pl-assignments/apply/` | 구현 완료 | 미배정 PL 또는 기존 PL의 센터 배정 변경 |
| `POST /api/rule-results/<result_id>/manual-pass/` | 구현 완료 | 점검 결과 수동 적합 처리와 메모 저장 |

외부 API 인증 토큰은 설정값 `LOCAL_REVIEW_API_TOKEN`이 있을 때 적용된다. 비어 있으면 기존 호환성을 위해 인증 없이 동작한다.

## 서버에서 PostgreSQL을 사용할 때의 접속 방식

Django 기본 설정(`myproject.settings`)은 `reference` alias로 PostgreSQL에 접속한다.

```text
Database alias: reference
Default database: gscert_reference
Default user: postgres
Default host: localhost
Default port: 5432
```

환경 변수 예시는 다음과 같다.

```powershell
$env:REFERENCE_PG_NAME = "gscert_reference"
$env:REFERENCE_PG_USER = "postgres"
$env:REFERENCE_PG_PASSWORD = "<PostgreSQL password>"
$env:REFERENCE_PG_HOST = "localhost"
$env:REFERENCE_PG_PORT = "5432"
```

서버에서 현재 운영 설정으로 Django 연결을 확인할 때는 다음처럼 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.settings
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.settings
```

`myproject.postgres_settings`와 `myproject.postgres_data_settings`는 전체 DB를 PostgreSQL로 놓고 확인하거나 데이터 적재 작업을 별도로 수행해야 할 때 사용하는 보조 설정이다. 일반 운영 서비스 기준은 `myproject.settings`다.

## 외부 PC에서 조회 테스트하는 방법

외부 PC에서는 PostgreSQL에 직접 접속하지 않고 API를 호출한다.

서버 주소가 `http://210.96.71.194:8000`이라고 가정하면 health API는 다음과 같이 확인한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/health/" -Method Get
```

정상 응답 예시는 다음과 같다.

```json
{
  "success": true,
  "ok": true,
  "server_time": "2026-06-18T..."
}
```

프로젝트 기준정보 조회 예시는 다음과 같다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.194:8000/api/local-review/projects/TTA-26-00727/metadata/?center=sangam" -Method Get
```

응답 주요 필드는 다음과 같다.

| 필드 | 설명 |
| --- | --- |
| `project_number` | 프로젝트 번호 |
| `company_name` | 회사명 |
| `product_name` | 제품명 |
| `pl_name` | 시험 PL |
| `wd_name` | WD |
| `request_date` | 신청일 |
| `contract_date` | 계약일 |
| `cert_date` | 인증일 |
| `start_date` | 시험 시작일 |
| `end_date` | 시험 종료일 |
| `review` | 현재 점검결과 |

`start_date`, `end_date`는 `reference_project.start_date`, `reference_project.expected_end_date` 기준으로 제공된다. 기준 행을 찾지 못하거나 값이 비어 있으면 빈 값으로 내려가고, 관련 점검규칙은 기준정보 없음으로 실패 처리한다.

## PostgreSQL 직접 접속을 열어야 하는 경우

권장하지는 않지만, 마이그레이션이나 관리 목적으로 일시적으로 외부 PostgreSQL 접속이 필요할 수 있다.

그 경우 필요한 서버 설정은 다음과 같다.

1. `postgresql.conf`의 `listen_addresses` 설정 확인
2. `pg_hba.conf`에 허용할 클라이언트 IP 범위 추가
3. Windows 방화벽 또는 서버 방화벽에서 `5432` 포트 허용
4. 강한 비밀번호 사용
5. 작업 완료 후 외부 접속 차단

예를 들어 `210.*` 대역 전체를 직접 허용하는 방식은 범위가 너무 넓다. 가능하면 실제 테스트 PC의 고정 IP만 제한적으로 허용하고, 작업이 끝나면 제거한다.

데스크톱 앱 배포 구조에서는 PostgreSQL 직접 접속을 열 필요가 없다.

## 서버 적용 순서

GitHub에서 최신 코드를 pull한 뒤 PostgreSQL `reference` DB migration을 먼저 맞춘다.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.settings
```

그 다음 Django 서버를 재시작한다. 워커는 이미 실행 중인 작업이 새 코드로 재점검하거나 수동 적합 재적용을 즉시 해야 하는 경우 재시작한다.

새 서버를 구축하는 경우에는 다음이 별도 배포 절차다.

- Python 패키지 설치 또는 갱신
- PostgreSQL 설치와 `gscert_reference` DB 준비
- `env.ps1` 또는 서비스 환경 변수에 `REFERENCE_PG_*` 등록
- `migrate --database=reference`
- `import_reference_db --source-xlsx main\data\reference.xlsx`
- `sync_reference_projects_from_sheet` 또는 weekly 동기화
- 서비스 재시작

---

# DB 스키마

DB 컬럼 정의의 기준은 이 문서다. 정의 원본 코드는 `main/models.py`, DB 분리 규칙은 `main/db_routers.py`, 접속 설정은 `myproject/settings.py`다.

## 데이터베이스(3개) 구성

Django `DATABASES` alias 3개로 나뉜다. 어떤 모델이 어느 DB로 가는지는 `DATABASE_ROUTERS`가 결정한다.

| alias | 엔진 | 위치 | 용도 |
|---|---|---|---|
| `default` | SQLite | `db.sqlite3` (프로젝트 루트) | 기타(레거시 `Job` 등). 세션/auth 등 Django 기본 테이블도 여기. |
| `workflow` | SQLite | `main/data/workflow.db` (**서버 로컬**) | 다운로드/점검 **실행 상태**(잡·프로젝트·결과·로그·락)와 유사 분석 작업. 서버마다 로컬. |
| `reference` | **PostgreSQL** | `gscert_reference` (주 서버, env로 접속) | **공유 기준 데이터**(점검규칙·프로젝트·PL 매핑·인증이력·수동 적합 메모). 여러 서버가 공유. |

- 접속 정보(`reference`): `REFERENCE_PG_NAME/USER/PASSWORD/HOST/PORT` 환경변수.
- 라우팅 규칙(`settings.py`): `WORKFLOW_MODEL_NAMES` → `workflow`, `REFERENCE_MODEL_NAMES` → `reference`, 그 외 → `default`.
- `DOWNLOAD_REVIEW_PROJECT_SOURCE = postgres` → 프로젝트 조회는 `reference`의 `reference_project` 우선.

## 테이블 요약

| 테이블 | 모델 | DB | 용도 |
|---|---|---|---|
| `reference_center_pl` | `ReferenceCenterPl` | reference | **센터별 PL 이름 매핑** (PL 이름 → 센터) |
| `reference_project` | `ReferenceProject` | reference | 프로젝트 기준정보(센터/회사/제품/PL/일정 등). 센터 해석의 소스 |
| `sw_data` | `SwData` | reference | GS 인증 획득 이력(인증획득목록 엑셀 적재분, 유사제품/이력 조회용) |
| `inspection_rule` | `DownloadReviewRule` | reference | 점검규칙 정의(두 서버 공유, admin 수정) |
| `inspection_manual_override` | `DownloadReviewManualOverride` | reference | 수동 적합 처리 메모(센터/프로젝트/규칙 기준, 재점검 재적용) |
| `automation_job` | `DownloadReviewJob` | workflow | 다운로드 검토 **잡** |
| `automation_job_project` | `DownloadReviewProject` | workflow | 잡에 속한 **프로젝트별** 처리 상태 |
| `inspection_result` | `DownloadReviewRuleResult` | workflow | 프로젝트별 **규칙 점검 결과** |
| `automation_log` | `DownloadReviewLog` | workflow | 잡/프로젝트 처리 로그 |
| `automation_lock` | `DownloadReviewLock` | workflow | 단일 워커 동시성 락(단일 행) |
| `server_time_control` | `ServerTimeControl` | workflow | 서버 시간 변경 lease(단일 행) |
| `server_time_audit` | `ServerTimeAudit` | workflow | 서버 시간 변경 감사 이력 |
| `main_similaranalysisjob` | `SimilarAnalysisJob` | workflow | 유사제품 자동 입력/비교 작업 상태와 결과 |
| `main_job` | `Job` | default | 레거시 잡(상태/최종 링크) |

크로스-DB 관계는 불가능하다. `inspection_result.rule_code`는 `inspection_rule`(다른 DB)로의 FK가 아니라 비정규화된 코드 문자열이다.

## reference DB (PostgreSQL, 공유 기준 데이터)

### `reference_center_pl` — 센터별 PL 이름 매핑

PL(프로젝트 리더) 이름을 센터에 매핑한다. `sync_reference_projects_from_sheet`가 기본 PL 목록을 채우고, `/download-review/`의 `PL 배정 목록` 모달이나 관리 명령의 `--assign-unknown-pl` 보조 옵션에서 배정한 추가 PL 매핑도 같은 테이블에 보존한다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | PK(auto) | |
| `center_code` | varchar(20), index | `bundang`/`sangam`/`yeongnam` |
| `center_label` | varchar(20) | 분당/상암/영남 |
| `name` | varchar(50), **unique** | **PL 이름(매핑 키)** |
| `display_order` | smallint | 정렬 순서 |
| `created_at`/`updated_at` | datetime | |

인덱스: `(center_code, name)`

### `reference_project` — 프로젝트 기준정보

프로젝트번호 단위 기준정보. 전체 다운로드의 센터 해석은 이 표의 `center_code`를 사용한다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | PK(auto) | |
| `project_number` | varchar(32), **unique**, index | 시험번호(예: `GS-A-23-0336`, `TTA-26-00009`) |
| `center_code` | varchar(20), index | 센터 코드 |
| `center_label` | varchar(20) | 센터 표시명 |
| `cert_date` | varchar(20) | 인증일 문자열. **동기화 경로에 따라 의미가 다르다**(아래 주의 참고) |
| `cert_committee_date` | date, index | 인증위 개최일. `sync_reference_projects_from_sheet`만 채우고, 읽는 곳은 프로젝트 목록 정렬뿐이다 |
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

`cert_date`는 의미가 혼재한다. `sync_new_certified_projects`(주간 자동)는 `SwData.cert_date`(인증서 발급일)를 복사하고, `sync_reference_projects_from_sheet`(수동 전체 동기화)는 인증위 개최일에서 만든 `M/D` 문자열을 넣는다. 점검 엔진의 `{인증위}` 기대값은 이 `cert_date`를 읽으므로 두 경로 중 어느 것이 마지막에 실행됐는지에 따라 값이 달라진다. 전용 date 컬럼인 `cert_committee_date`는 존재하지만 엔진이 읽지 않고 프로젝트 목록 정렬에만 쓰인다. 미결사항으로 `00_README.md`와 `08_artifact_autofill.md`에 기록돼 있다.

### `sw_data` — GS 인증 획득 이력

인증획득목록 엑셀을 주간 동기화로 적재한 참조 데이터(구 `reference.db` `sw_data`). 점검 엔진의 `{시작일}`/`{종료일}`은 이 표에서 직접 조회한다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `serial_number` | int, **PK** | 일련번호 |
| `cert_number` | text | 인증번호 |
| `cert_date` | text | 인증일 |
| `company`/`product` | text | 회사/제품 |
| `grade` | text | 등급 |
| `test_number` | text | 시험번호(프로젝트번호) |
| `sw_category`/`product_desc`/`total_wd`/`renewal`/`notes`/`date_range`/`test_lab`/`start_date`/`end_date` | text | 부가 정보 |

### `inspection_rule` — 점검규칙 정의

점검규칙을 주 서버에 단일 저장해 194/241이 공유하고 Django admin에서 수정한다. 수정 절차는 `02_inspection_rules.md`를 본다.

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

### `inspection_manual_override` — 수동 적합 처리

재점검 후 이전 `inspection_result`가 정리되어도 수동 적합 메모가 유지되도록, 결과 FK가 아니라 `center_code + project_number + rule_code + sub_check_key` 키로 저장한다. 같은 키의 override가 있으면 해당 세부항목만 `pass`로 재적용하고 UI에 보라색 정상 배지와 메모를 표시한다. `sub_check_key`가 빈 문자열인 기존 규칙 단위 override는 호환을 위해 규칙 전체에 적용한다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `center_code` | varchar(20), index | 센터 코드 |
| `project_number` | varchar(32), index | 프로젝트번호 |
| `rule_code` | varchar(80), index | 규칙 코드 |
| `sub_check_key` | varchar(80) | 세부항목 키. 규칙 전체 override는 빈 문자열 |
| `rule_name` | varchar(255) | 표시용 규칙명 |
| `memo` | text | 수동 적합 처리 사유(필수) |
| `created_by` | varchar(120) | 요청 IP 등 |
| `created_at`/`updated_at`/`last_applied_at` | datetime | |

제약: `(center_code, project_number, rule_code, sub_check_key)` unique.

## workflow DB (SQLite, 서버 로컬 실행 상태)

### `automation_job` — 다운로드 검토 잡 (`DownloadReviewJob`)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `center_code` | varchar(20), index | 잡 센터 |
| `status` | varchar(20), index | `queued`/`running`/`completed`/`failed`/`canceled`. `scheduled`는 legacy 호환값 |
| `requested_at`/`queued_at`/`started_at`/`completed_at`/`canceled_at`/`available_after` | datetime | 상태 시각 |
| `progress_message` | varchar(500) | 진행 메시지 |
| `requested_project_count`/`completed_project_count`/`failed_project_count` | int | 집계 |
| `selected_projects_json` | json | 선택 프로젝트 목록 |
| `requested_ip` | inet | 요청 IP |
| `last_error_message` | text | |
| `worker_pid`/`worker_host`/`worker_heartbeat_at` | | 워커 추적 |
| `created_at`/`updated_at` | datetime | |

### `automation_job_project` — 프로젝트별 처리 (`DownloadReviewProject`)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `job_id` | FK → automation_job | |
| `center_code` | varchar(20), index | |
| `project_number` | varchar(32), index | 시험번호 |
| `ecm_row_json` | json | 프로젝트 dict(회사/제품/PL/WD/일정/인증일). `reference_project`와 `SwData` 병합 결과 |
| `status` | varchar(20), index | `queued`/`running`/`downloaded`/`inspecting`/`completed`/`failed`/`skipped` |
| `review_status` | varchar(20), index | `unreviewed`/`completed`/`needs_fix`/`held` |
| `download_dir`/`zip_path`/`zip_file_name`/`zip_deleted_at` | | 산출물 경로 |
| `current_step`/`error_message`/`error_detail`/`retry_count` | | 진행/오류 |
| `started_at`/`completed_at`/`created_at`/`updated_at` | datetime | |

제약: `(job, project_number)` unique.

### `inspection_result` — 규칙 점검 결과 (`DownloadReviewRuleResult`)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `job_project_id` | FK → automation_job_project | |
| `rule_code`/`rule_name` | | 규칙 식별(비정규화, cross-DB라 FK 아님) |
| `sequence` | smallint | |
| `file_path`/`file_name` | | 대상 파일 |
| `status` | varchar(20), index | `pass`/`fail`/`warning`/`error` |
| `expected`/`actual`/`message` | text | 기대/실제/메시지 |
| `raw_detail_json` | json | 세부항목, 증거, 산출 변수 |
| `created_at` | datetime | |

### `automation_log` — 처리 로그 (`DownloadReviewLog`)

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

### `automation_lock` — 워커 동시성 락 (`DownloadReviewLock`)

단일 행(id=1)으로 워커 동시 실행을 제어한다.

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | smallint, PK(기본 1) | |
| `locked` | bool | 잠금 여부 |
| `owner` | varchar(80) | 점유자 |
| `job_id` | FK(nullable) → automation_job | |
| `locked_at`/`heartbeat_at`/`updated_at` | datetime | |
| `note` | varchar(255) | |

### `server_time_control` / `server_time_audit`

`server_time_control`은 단일 행(id=1)으로 시간 변경 선점, 작업자 이름, PIN 해시, revision, 단조 타이머, 복구 상태를 관리한다. 상태는 `idle`/`changing`/`active`/`restoring`/`recovery_failed`다. `server_time_audit`은 이벤트 순번, 작업자 이름, 요청 IP, revision, 관측 OS 시각, 정상 추정 시각과 공개 가능한 처리 메타데이터를 저장하며 PIN과 내부 오류 문자열은 저장하지 않는다. 동작은 `07_server_time_control.md`를 본다.

### `main_similaranalysisjob` — 유사제품 자동 입력 작업 (`SimilarAnalysisJob`)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `status` | varchar(20), index | `queued`/`running`/`completed`/`failed` |
| `progress` | smallint | 진행률 |
| `progress_message` | varchar(500) | 진행 메시지 |
| `input_files_json` | json | 입력 파일 목록 |
| `result_json` | json | 분석 결과 |
| `error_message` | text | |
| `created_at`/`started_at`/`completed_at`/`updated_at` | datetime | |

## default DB (SQLite)

### `main_job` — 레거시 잡 (`Job`)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | UUID, PK | |
| `status` | varchar(20) | `PENDING`/`RUNNING`/`DONE`/`ERROR` |
| `final_link` | url | |
| `error` | text | |
| `created_at`/`updated_at` | datetime | |

Django 기본 테이블(auth/sessions/admin 등)도 `default` DB에 있다.

---

# 기준정보 동기화

`reference_project`는 두 경로로 채워진다. 어느 경로가 마지막에 실행됐는지에 따라 같은 컬럼의 출처가 달라지므로, 값의 출처가 중요한 작업에서는 이 절을 먼저 확인한다.

| 명령 | 실행 방식 | 채우는 값의 출처 |
| --- | --- | --- |
| `sync_new_certified_projects --since-serial <N>` | `main/utils/weekly.py`의 주간(W) 동기화가 자동 호출 | 회사명/제품명/PL/WD/시험기간/인증일은 `SwData`(인증획득목록 엑셀). 신청일/계약일만 인증위 구글시트에서 프로젝트번호로 보완한다. 시트에서 프로젝트번호를 못 찾으면 그 건은 건너뛴다 |
| `sync_reference_projects_from_sheet` | 서버 관리 콘솔의 Google Sheets 동기화 버튼 또는 수동 실행 | 모든 값을 인증위 구글시트에서 가져와 덮어쓴다. `reference_center_pl`(PL-센터 매핑)도 이 명령이 채운다 |

산출물 자동 입력 기능의 공통 변수는 위 구 인증위 시트가 아니라 센터별 "GS 정보 확인용" 신규 구글시트(`main/utils/google_sheet_reference.py`)를 출처로 삼는다. 상세는 `08_artifact_autofill.md`를 본다.

## 저장 구조

| DB 객체 | 용도 |
| --- | --- |
| `reference_project` | 전체 센터 프로젝트 목록 원본 테이블 |
| `reference_center_pl` | PL 이름 기준 센터 매핑 테이블 |
| `reference_project_sangam` | 상암 프로젝트 조회용 view |
| `reference_project_bundang` | 분당 프로젝트 조회용 view |
| `reference_project_yeongnam` | 영남 프로젝트 조회용 view |

`reference_project`는 프로젝트번호를 고유키로 쓴다. 다시 동기화하면 회사명, 제품명, WD, 신청일, 계약일, 시작일, 종료예정일, 시험원, 센터 정보는 갱신하고 기존 점검결과(`review_result`, `artifact_results_json`)는 유지한다.

## 인증위 시트 파싱 규칙

| 항목 | 규칙 |
| --- | --- |
| 인증위 날짜 | B열에서 `yyyy년 m월 d일(요일)` 형식의 날짜를 찾고, 뒤에 시간이 붙어도 날짜만 사용 |
| 데이터 시작 | 날짜 행 기준 3행 아래의 헤더 다음 행부터 읽음 |
| 데이터 범위 | B열 값이 이어지는 동안 B~I열을 프로젝트 행으로 해석 |
| 회사명/제품명 | B열에서 괄호와 괄호 안 내용을 제거한 뒤 `-` 기준 1회 분리. 맨 앞의 법인 표시 괄호는 제거하지 않는다 |
| 센터 | H열 시험원을 쉼표로 나눈 첫 번째 이름을 `reference_center_pl`과 매칭 |
| 미배정 PL | 매핑에 없으면 프로젝트를 버리지 않고 `center_code=unknown`, `center_label=미분류`로 저장 |

## 실행

비밀번호는 코드나 문서에 저장하지 않고 실행 환경변수로만 지정한다.

```powershell
$env:REFERENCE_PG_HOST = "localhost"
$env:REFERENCE_PG_PORT = "5432"
$env:REFERENCE_PG_NAME = "gscert_reference"
$env:REFERENCE_PG_USER = "postgres"
$env:REFERENCE_PG_PASSWORD = "<PostgreSQL password>"

.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet --settings=myproject.settings
```

파싱만 확인하려면 DB 접속 없이 dry-run을 사용한다.

```powershell
.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet --dry-run --no-schema-check --settings=myproject.ui_mock_settings
```

## 미배정 PL 배정

운영자가 미배정 PL을 센터에 배정할 때는 `/download-review/`의 `PL 배정 목록` 모달을 사용한다.

- `GET /api/pl-assignments/`가 센터별 PL과 미배정 PL 목록을 내려준다.
- `POST /api/pl-assignments/apply/`가 변경 목록을 저장한다.
- 미배정 PL을 센터로 옮기면 `reference_center_pl`에 매핑을 만들고, 아직 점검하지 않은 미배정 프로젝트도 새 센터로 이동한다.
- 이미 점검된 프로젝트는 자동 이동하지 않는다. 완료된 점검 결과가 다른 센터 목록으로 옮겨가는 것을 막기 위해서다.

관리 명령의 `--assign-unknown-pl` 옵션은 터미널에서 번호를 입력해 즉시 배정하는 보조 경로다. 서버 콘솔이나 웹 요청처럼 비대화형으로 실행되는 경로에서는 사용하지 않는다.
