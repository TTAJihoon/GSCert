# Google Sheet 프로젝트 목록 PostgreSQL 적재 가이드

## 목적

인증위 Google Sheet에서 프로젝트 목록을 읽어 PostgreSQL `reference_project` 테이블에 저장한다.
저장된 값은 `/download-review/` 프로젝트 체크박스 목록, Windows 프로그램 프로젝트 메타데이터 조회, 점검규칙 변수 추출에 사용한다.

센터 구분은 Google Sheet의 `시험원` 값에서 첫 번째 이름을 추출한 뒤, 미리 정의한 센터별 PL 이름 목록과 매칭해서 결정한다.

## 대상 Google Sheet

기본 설정:

```text
Spreadsheet ID: 1KvzcX3zVJmUx02iIogRj0sRjGD1o7ae4xuX2DFGn_T8
gid: 740274777
CSV export URL:
https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}
```

구현 위치:

```text
main/utils/ecm_reference_sheet.py
main/management/commands/sync_reference_projects_from_sheet.py
```

## Sheet 파싱 규칙

시트는 날짜 블록 단위로 읽는다.

1. B열에서 `yyyy년 m월 d일(요일)` 형식의 날짜를 찾는다.
2. 해당 날짜를 `인증위 날짜`로 사용한다.
3. 날짜가 있는 행 기준 `+3행`부터 프로젝트 목록을 읽는다.
4. B열 값이 연속으로 존재하는 동안 같은 날짜 블록의 프로젝트로 본다.
5. 다음 날짜 형식이 다시 나오면 새 날짜 블록으로 전환한다.

예시:

```text
B15 = 2026년 6월 25일(목)
프로젝트 목록 시작 = 18행
B18~I18, B19~I19 ... 를 프로젝트 행으로 해석
```

## Sheet 열 매핑

현재 구현은 날짜 블록 안에서 B열부터 I열까지를 사용한다.

| Sheet 열 | 의미 | 저장 컬럼 |
| --- | --- | --- |
| B | 회사(제품) 원문 | `raw_company_product` |
| B | 회사명 | `company` |
| B | 제품명 | `product` |
| C | WD | `wd` |
| D | 신청일 | `request_date` |
| E | 계약일 | `contract_date` |
| F | 시작일 | `start_date` |
| G | 종료예정일 | `expected_end_date` |
| H | 시험원 | `pl` |
| H | 첫 번째 시험원 | `primary_tester` |
| I | 프로젝트 번호 | `project_number` |
| 날짜 블록 B열 | 인증위 날짜 | `cert_committee_date`, `cert_date` |

회사명/제품명 분리 규칙:

```text
1. B열 값에서 괄호와 괄호 안 내용을 제거
2. 남은 문자열을 첫 번째 '-' 기준으로 분리
3. '-' 앞은 회사명, 뒤는 제품명
```

시험원 분리 규칙:

```text
H열 값을 ',', '，', '、', '/' 중 하나로 나눔
첫 번째 값을 공백 제거 후 primary_tester로 사용
```

프로젝트 번호 유효성:

```text
^[A-Z]{2,5}-\d{2}-\d{4,5}$
```

유효하지 않은 행은 적재하지 않는다.

## 센터 판정 규칙

센터는 `primary_tester`를 센터별 이름 목록과 비교해서 결정한다.

| 센터 | center_code | 매칭 기준 |
| --- | --- | --- |
| 분당 | `bundang` | 분당 PL 이름 목록 |
| 상암 | `sangam` | 상암 PL 이름 목록 |
| 영남 | `yeongnam` | 영남 PL 이름 목록 |
| 미분류 | `unknown` | 어느 목록에도 없는 이름 |

센터별 이름 목록은 코드에 저장되어 있다.

```text
main/utils/ecm_reference_sheet.py
CENTER_PL_NAMES
```

DB에는 전화번호를 저장하지 않고 이름만 저장한다.
센터별 이름 목록은 `reference_center_pl` 테이블에도 적재한다.

## PostgreSQL 저장 구조

| DB 객체 | 목적 |
| --- | --- |
| `reference_project` | 전체 센터 프로젝트 목록 원본 테이블 |
| `reference_center_pl` | PL 이름 기준 센터 매핑 테이블 |
| `reference_project_sangam` | 상암 프로젝트 조회용 view |
| `reference_project_bundang` | 분당 프로젝트 조회용 view |
| `reference_project_yeongnam` | 영남 프로젝트 조회용 view |

`reference_project.project_number`가 고유키다.
같은 프로젝트 번호가 다시 들어오면 아래 기준정보는 갱신한다.

```text
center_code, center_label, cert_date, cert_committee_date,
company, product, pl, primary_tester, wd,
request_date, contract_date, start_date, expected_end_date,
raw_company_product, source_spreadsheet_id, source_gid,
source_row_number, source_payload_json
```

점검결과 관련 값은 프로젝트 목록 재동기화로 덮어쓰지 않는다.

## 실행 명령

운영 DB에 적재:

```powershell
$env:GSCERT_DB_HOST = "210.96.71.241"
$env:GSCERT_DB_PORT = "5432"
$env:GSCERT_DB_NAME = "gscert_prod"
$env:GSCERT_DB_USER = "postgres"
$env:GSCERT_DB_PASSWORD = "<PostgreSQL password>"

.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet `
  --settings=myproject.postgres_data_settings
```

시트 파싱만 확인:

```powershell
.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet `
  --dry-run `
  --no-schema-check `
  --settings=myproject.ui_mock_settings
```

CSV 파일로 재현 테스트:

```powershell
.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet `
  --source-csv C:\temp\reference_projects.csv `
  --dry-run `
  --no-schema-check `
  --settings=myproject.ui_mock_settings
```

## 적재 후 조회 방식

웹 프로젝트 목록은 다음 API에서 센터별로 조회한다.

```text
GET /api/projects/?center=bundang
GET /api/projects/?center=sangam
GET /api/projects/?center=yeongnam
```

Windows 프로그램은 프로젝트 번호로 메타데이터를 조회한다.

```text
GET /api/local-review/projects/{project_number}/metadata/?center=bundang
```

운영 설정에서 PostgreSQL 기준정보를 사용하려면 다음 값이 필요하다.

```text
DOWNLOAD_REVIEW_PROJECT_SOURCE=postgres
```

## 운영 확인 SQL

센터별 건수:

```sql
SELECT center_code, center_label, COUNT(*)
FROM reference_project
GROUP BY center_code, center_label
ORDER BY center_code;
```

미분류 시험원 확인:

```sql
SELECT primary_tester, COUNT(*)
FROM reference_project
WHERE center_code = 'unknown'
GROUP BY primary_tester
ORDER BY COUNT(*) DESC, primary_tester;
```

특정 프로젝트 확인:

```sql
SELECT project_number, center_code, company, product, wd,
       request_date, contract_date, start_date, expected_end_date, pl
FROM reference_project
WHERE project_number = 'TTA-26-00195';
```

센터별 view 확인:

```sql
SELECT COUNT(*) FROM reference_project_bundang;
SELECT COUNT(*) FROM reference_project_sangam;
SELECT COUNT(*) FROM reference_project_yeongnam;
```

## 수정이 필요한 경우

시험원 이름이 새로 추가되면 다음 순서로 처리한다.

1. `main/utils/ecm_reference_sheet.py`의 `CENTER_PL_NAMES`에 이름 추가
2. dry-run으로 센터별 건수와 미분류 이름 확인
3. 운영 DB 적재 명령 실행
4. `/api/projects/?center=...`에서 원하는 센터 목록에 표시되는지 확인

Sheet 열 구조가 바뀌면 `parse_project_row()`의 `_cell(row, index)` 매핑을 수정해야 한다.
CSV index는 0부터 시작하므로 현재 B열은 index `1`, I열은 index `8`이다.
