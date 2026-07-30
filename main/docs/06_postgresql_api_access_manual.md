# PostgreSQL 및 서버 API 조회 매뉴얼

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

운영 기준에서 프로젝트 기준정보, PL 매핑, 인증 이력, 점검규칙, 수동 적합 메모는 PostgreSQL `reference` DB를 사용한다. 작업 상태, 점검 결과 원본, 유사 분석 작업은 서버 로컬 `workflow.db`에 남긴다. 상세 구조는 `13_db_schema.md`가 기준이다.

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

수동 적합 메모를 workflow SQLite에 임시 저장했던 서버라면 한 번만 이관 명령을 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py migrate_manual_overrides_to_reference --settings=myproject.settings
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
