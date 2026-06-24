# Reference Project Sheet Sync

## 목적

인증위 Google Sheet의 프로젝트 목록을 PostgreSQL reference DB에 적재해서 웹과 Windows 프로그램이 같은 프로젝트 기준정보를 사용하도록 한다.

## 저장 구조

| DB 객체 | 용도 |
| --- | --- |
| `reference_project` | 전체 센터 프로젝트 목록 원본 테이블 |
| `reference_center_pl` | PL 이름 기준 센터 매핑 테이블 |
| `reference_project_sangam` | 상암 프로젝트 조회용 view |
| `reference_project_bundang` | 분당 프로젝트 조회용 view |
| `reference_project_yeongnam` | 영남 프로젝트 조회용 view |

`reference_project`는 프로젝트번호를 고유키로 사용한다. Google Sheet를 다시 동기화하면 회사명, 제품명, WD, 신청일, 계약일, 시작일, 종료예정일, 시험원, 센터 정보는 갱신하고 기존 점검결과는 유지한다.

## 파싱 규칙

| 항목 | 규칙 |
| --- | --- |
| 인증위 날짜 | B열에서 `yyyy년 m월 d일(요일)` 형식의 날짜를 찾고, 뒤에 시간이 붙어도 날짜만 사용 |
| 데이터 시작 | 날짜 행 기준 3행 아래의 헤더 다음 행부터 읽음 |
| 데이터 범위 | B열 값이 이어지는 동안 B~I열을 프로젝트 행으로 해석 |
| 회사명/제품명 | B열에서 괄호와 괄호 안 내용을 제거한 뒤 `-` 기준 1회 분리 |
| 센터 | H열 시험원을 `,`로 나눈 첫 번째 이름을 `reference_center_pl`과 매칭 |
| 미분류 | PL 이름이 매핑에 없으면 `center_code=unknown`, `center_label=미분류`로 저장 |

## 실행

비밀번호는 코드나 문서에 저장하지 않고 실행 환경변수로만 지정한다.

```powershell
$env:GSCERT_DB_HOST = "210.96.71.241"
$env:GSCERT_DB_PORT = "5432"
$env:GSCERT_DB_NAME = "gscert_prod"
$env:GSCERT_DB_USER = "postgres"
$env:GSCERT_DB_PASSWORD = "<PostgreSQL password>"

.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet `
  --settings=myproject.postgres_data_settings
```

파싱만 확인하려면 DB 접속 없이 dry-run을 사용한다.

```powershell
.\.venv\Scripts\python.exe manage.py sync_reference_projects_from_sheet `
  --dry-run `
  --no-schema-check `
  --settings=myproject.ui_mock_settings
```

## API 사용

PostgreSQL 프로젝트 목록을 웹/API에서 사용하려면 운영 설정에서 다음 값이 적용되어야 한다.

```text
DOWNLOAD_REVIEW_PROJECT_SOURCE=postgres
```

센터별 프로젝트 목록 API:

```text
GET /api/projects/?center=sangam
GET /api/projects/?center=bundang
GET /api/projects/?center=yeongnam
```

Windows 프로그램 메타데이터 API:

```text
GET /api/local-review/projects/{project_number}/metadata/?center=sangam
```

## 현재 접속 이슈

2026-06-24 현재 개발 PC에서 `210.96.71.241:5432` 접속 시 PostgreSQL이 현재 접속 IP `210.96.71.254`를 `pg_hba.conf`에서 허용하지 않아 적재가 차단되었다. 서버에서 해당 IP 또는 필요한 210 대역을 허용한 뒤 위 실행 명령을 다시 수행하면 된다.
