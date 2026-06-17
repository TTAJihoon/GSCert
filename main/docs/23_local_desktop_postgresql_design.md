# 로컬 Windows 점검 앱 및 PostgreSQL 전환 설계

## 1. 결정 사항

- 배포 형태: 완전한 Windows 데스크톱 앱으로 개발하고 최종 사용자는 `.exe` 파일을 실행한다.
- 실행 방식: 사용자가 로컬 PC에서 점검 대상 폴더를 선택하고 `점검 수행`을 클릭하면 해당 PC에서 파일 점검을 수행한다.
- 서버 역할: 서버는 프로젝트 기준정보를 제공하는 API와 중앙 PostgreSQL DB를 담당한다.
- DB 접속 방식: 데스크톱 앱은 PostgreSQL에 직접 접속하지 않고 Django API만 호출한다.
- PostgreSQL 위치: 기존 Django 서버와 같은 서버에서 운영한다.
- PostgreSQL DB 이름: `gscert_prod`
- PostgreSQL 앱 계정: `gscert_app`
- PostgreSQL 관리자 계정: `postgres`
- SSL: 현재는 사용하지 않는다. 내부 테스트 단계에서는 HTTP/API 호출로 진행하고, 운영 전 HTTPS 적용을 권장한다.
- 외부 접속: 외부 PC는 PostgreSQL `5432` 포트가 아니라 Django API 포트로만 접근한다.

## 2. 권장 아키텍처

```text
사용자 Windows PC
  - gscert-local-review.exe
  - 로컬 점검 대상 폴더 선택
  - 기존 점검 엔진 실행
  - 결과 화면 표시 및 파일 저장
        |
        | HTTP/HTTPS API
        v
Django 서버
  - 프로젝트 기준정보 API
  - 인증/권한
  - 필요 시 점검 이력 수집 API
        |
        | localhost:5432
        v
PostgreSQL
  - gscert_prod
  - 프로젝트 기준정보
  - 작업/점검 이력
  - 기존 SQLite 데이터 통합 이전
```

이 구조를 선택하는 이유는 데스크톱 앱에 DB 비밀번호를 넣지 않아도 되고, DB 스키마가 바뀌어도 앱 전체를 매번 재배포하지 않고 서버 API를 먼저 조정할 수 있기 때문이다. 또한 PostgreSQL 외부 개방 범위를 최소화할 수 있어 운영 보안상 더 안전하다.

## 3. 데이터 이전 범위

기존 SQLite 데이터는 PostgreSQL `gscert_prod`로 통합 이전한다.

| 기존 데이터 | 현재 용도 | PostgreSQL 이전 방향 |
| --- | --- | --- |
| `db.sqlite3` | Django 기본 DB | `default` DB로 이전 |
| `main/data/workflow.db` | ECM 다운로드 점검 작업/결과/로그 | 같은 PostgreSQL DB의 `workflow` alias로 이전 |
| `main/data/ecmlist.db` | 프로젝트 기준정보 | 프로젝트 기준정보 테이블로 이전 |
| `main/data/ecmlist2.db` | 보조 프로젝트 기준정보 | 프로젝트 기준정보 또는 별도 보조 테이블로 이전 |
| `main/data/reference.db` | 참조 데이터 | 규칙/참조 테이블로 이전 |

초기 전환에서는 Django의 `default`와 `workflow` alias를 모두 같은 PostgreSQL DB(`gscert_prod`)에 연결한다. 기존 라우터 구조는 유지해서 workflow 모델은 `workflow` alias를 통해 마이그레이션하고, 일반 Django 모델은 `default` alias를 통해 마이그레이션한다.

## 4. 서버 환경 변수

서버 배포 시 다음 환경 변수를 사용한다.

```powershell
$env:GSCERT_DB_NAME = "gscert_prod"
$env:GSCERT_DB_USER = "gscert_app"
$env:GSCERT_DB_PASSWORD = "<gscert_app 비밀번호>"
$env:GSCERT_DB_HOST = "127.0.0.1"
$env:GSCERT_DB_PORT = "5432"
```

SSL이 필요한 환경으로 바뀌면 다음 값을 추가한다.

```powershell
$env:GSCERT_DB_SSLMODE = "require"
```

현재 결정 기준에서는 SSL을 사용하지 않으므로 `GSCERT_DB_SSLMODE`은 설정하지 않는다.

## 5. PostgreSQL 서버 설정 원칙

- PostgreSQL은 Django 서버 내부에서만 접근하도록 `127.0.0.1:5432` 중심으로 구성한다.
- 외부 PC의 `210.*` 대역은 PostgreSQL에 직접 접속하지 않는다.
- 외부 PC는 Django API에만 접근한다.
- `postgres` 관리자 계정은 마이그레이션/운영 관리에만 사용한다.
- 실제 앱과 Django 서비스는 `gscert_app` 계정을 사용한다.
- 데스크톱 앱에는 DB 접속 정보나 관리자 비밀번호를 포함하지 않는다.

## 6. 데스크톱 앱 기능 범위

1. 사용자가 로컬 폴더를 선택한다.
2. 앱이 폴더명, ZIP 파일명, 파일명에서 프로젝트 번호를 추정한다.
3. 프로젝트 번호가 없거나 여러 개면 사용자가 직접 선택 또는 입력한다.
4. 앱이 Django API로 프로젝트 기준정보를 조회한다.
5. 기존 점검 엔진을 로컬 파일 대상으로 실행한다.
6. 점검 결과를 화면에 표시한다.
7. 결과 상세 팝업, 규칙별 결과, 엑셀/HTML 내보내기를 제공한다.
8. 필요 시 서버에 점검 요약만 업로드한다.

## 7. 서버 API 초안

초기 데스크톱 앱에는 최소 API만 필요하다.

| API | 용도 | 응답 주요 필드 |
| --- | --- | --- |
| `GET /api/local-review/health/` | 서버 연결 확인 | `ok`, `server_time` |
| `GET /api/local-review/projects/<project_number>/metadata/` | 프로젝트 기준정보 조회 | `project_number`, `company_name`, `product_name`, `pl_name`, `wd_name`, `request_date`, `contract_date`, `cert_date`, `start_date`, `end_date` |

추후 중앙 이력 관리가 필요하면 다음 API를 추가한다.

| API | 용도 |
| --- | --- |
| `POST /api/local-review/runs/` | 로컬 점검 실행 요약 업로드 |
| `POST /api/local-review/runs/<run_id>/results/` | 규칙별 결과 업로드 |

## 8. 서버 기준정보 변수 정리

현재 로컬 파일에서 직접 추출하기 어려운 값은 서버 기준정보 API로 제공한다.

| 변수 | 현재 의미 | 서버 제공 대안 |
| --- | --- | --- |
| 프로젝트 번호 | 점검 대상 식별자 | 파일명/폴더명에서 추정 후 API 조회 |
| 회사명 | 제출 기관 또는 업체명 | 프로젝트 기준정보 테이블 |
| 제품명 | 인증 대상 제품명 | 프로젝트 기준정보 테이블 |
| PL | 프로젝트 담당자 | 프로젝트 기준정보 테이블 |
| WD | 작업 담당자 | 프로젝트 기준정보 테이블 |
| 접수일 | ECM 접수 기준 날짜 | 프로젝트 기준정보 테이블 |
| 계약일 | 계약 기준 날짜 | 프로젝트 기준정보 테이블 |
| 인증일 | 인증서 또는 완료 기준 날짜 | 프로젝트 기준정보 테이블 |
| 시험 시작일 | 시험 기간 검증 기준 | 프로젝트 기준정보 테이블 |
| 시험 종료일 | 시험 기간 검증 기준 | 프로젝트 기준정보 테이블 |

사용자가 더 정확한 추출 위치를 제공하면 서버 기준정보 테이블의 컬럼명과 API 응답 필드를 그 기준에 맞춰 확정한다.

## 9. 구현 단계

### 1단계: 서버 전환 준비

- PostgreSQL 설정용 Django settings 모듈을 추가한다.
- PostgreSQL 드라이버를 의존성에 추가한다.
- 기존 SQLite 라우팅 구조와 PostgreSQL alias 연결 방식을 문서화한다.

### 2단계: PostgreSQL DB 생성 및 계정 구성

- `gscert_prod` DB를 생성한다.
- `gscert_app` 계정을 생성한다.
- Django 서버에서 `127.0.0.1:5432`로 접속되는지 확인한다.
- 외부 PC에서 PostgreSQL 직접 접속은 허용하지 않는다.

### 3단계: 데이터 마이그레이션

- 기존 SQLite 데이터를 백업한다.
- Django 기본 테이블과 workflow 테이블을 PostgreSQL로 이전한다.
- 프로젝트 기준정보 SQLite 테이블을 PostgreSQL 모델 또는 관리 테이블로 이전한다.
- 이전 후 건수와 샘플 프로젝트 조회 결과를 비교한다.

### 4단계: 기준정보 API 개발

- 프로젝트 번호 기준 metadata API를 추가한다.
- 기존 점검 엔진에서 필요한 날짜/담당자/회사/제품 정보를 API 응답으로 제공한다.
- 서버 연결 실패 시 데스크톱 앱에서 사용자가 수동 입력할 수 있는 fallback을 둔다.

### 5단계: Windows 데스크톱 앱 개발

- Python 기반 데스크톱 앱으로 개발한다.
- UI 프레임워크는 PySide6를 우선 검토한다.
- 기존 점검 엔진을 최대한 재사용한다.
- 로컬 결과 저장소는 SQLite를 사용한다.

### 6단계: `.exe` 패키징

- PyInstaller로 단일 실행 파일 또는 배포 폴더를 만든다.
- 내부 테스트용 서명 없는 패키지를 먼저 배포한다.
- 운영 배포 시 코드 서명과 버전 업데이트 정책을 정한다.

## 10. 서버 반영 방식

GitHub에 변경사항을 push한 뒤 서버에서 해당 브랜치 또는 배포 브랜치를 pull하면 코드 변경은 반영된다. 다만 다음 항목은 서버에서 별도로 수행해야 한다.

- Python 패키지 설치 또는 갱신
- 환경 변수 설정
- PostgreSQL DB/계정 생성
- Django migration 실행
- 서비스 재시작

즉, 코드 변경은 `git pull`로 가져오지만 DB 생성, 마이그레이션, 서비스 재시작은 배포 절차에 포함해야 한다.

## 11. pgAdmin에서 확인할 항목

pgAdmin에서 다음 항목을 확인하면 서버 전환 작업을 진행할 수 있다.

| 확인 항목 | pgAdmin 위치 |
| --- | --- |
| Host/IP | 서버 등록 정보의 `Host name/address` |
| Port | 서버 등록 정보의 `Port` |
| PostgreSQL 버전 | 서버 선택 후 Dashboard 또는 Properties |
| 관리자 계정 | Login/Group Roles의 `postgres` |
| 기존 DB 목록 | Databases |
| 외부 접속 허용 여부 | 서버 방화벽, `postgresql.conf`, `pg_hba.conf` |
| SSL 사용 여부 | 서버 등록 정보의 SSL 탭 또는 서버 설정 |

현재 전달받은 정보 기준으로는 DB 이름을 새로 만들고, 앱 계정도 새로 만드는 전환 절차가 필요하다.
