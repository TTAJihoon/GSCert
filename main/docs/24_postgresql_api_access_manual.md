# PostgreSQL 및 서버 API 조회 매뉴얼

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

## 현재 구현된 상태

현재 구현된 서버 API는 다음과 같다.

| API | 상태 | 설명 |
| --- | --- | --- |
| `GET /api/local-review/health/` | 구현 완료 | 서버 연결 상태 확인 |
| `GET /api/local-review/projects/<project_number>/metadata/?center=sangam` | 구현 완료 | 프로젝트 기준정보 조회 |

아직 완료되지 않은 항목은 다음과 같다.

| 항목 | 상태 |
| --- | --- |
| PostgreSQL DB `gscert_prod` 생성 | 미완료 |
| PostgreSQL 앱 계정 `gscert_app` 생성 | 미완료 |
| 기존 SQLite 데이터를 PostgreSQL로 이전 | 미완료 |
| 기준정보 조회 소스를 SQLite에서 PostgreSQL로 전환 | 미완료 |
| 외부 API 인증 토큰 적용 | 미완료 |

즉, API 경로는 준비됐지만 현재 기준정보 조회는 아직 기존 SQLite 기준정보 DB를 사용한다. PostgreSQL로 실제 조회하려면 DB 생성, 계정 생성, 데이터 이전, 조회 repository 전환이 추가로 필요하다.

## 서버에서 PostgreSQL을 사용할 때의 접속 방식

Django 서버는 PostgreSQL에 로컬 접속한다.

```text
Host: 127.0.0.1
Port: 5432
Database: gscert_prod
User: gscert_app
```

환경 변수 예시는 다음과 같다.

```powershell
$env:GSCERT_DB_NAME = "gscert_prod"
$env:GSCERT_DB_USER = "gscert_app"
$env:GSCERT_DB_PASSWORD = "<gscert_app 비밀번호>"
$env:GSCERT_DB_HOST = "127.0.0.1"
$env:GSCERT_DB_PORT = "5432"
```

현재 SSL은 사용하지 않는 것으로 결정했으므로 `GSCERT_DB_SSLMODE`은 설정하지 않는다.

PostgreSQL settings 모듈은 다음 파일에 있다.

```text
myproject/postgres_settings.py
```

서버에서 PostgreSQL 설정으로 Django를 확인할 때는 다음처럼 settings를 지정한다.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.postgres_settings
```

운영 서비스도 같은 settings를 사용하도록 서비스 실행 명령 또는 환경 변수를 조정해야 한다.

## 외부 PC에서 조회 테스트하는 방법

외부 PC에서는 PostgreSQL에 직접 접속하지 않고 API를 호출한다.

서버 주소가 `http://210.96.71.241:8000`이라고 가정하면 health API는 다음과 같이 확인한다.

```powershell
Invoke-RestMethod -Uri "http://210.96.71.241:8000/api/local-review/health/" -Method Get
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
Invoke-RestMethod -Uri "http://210.96.71.241:8000/api/local-review/projects/TTA-26-00727/metadata/?center=sangam" -Method Get
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

현재 `start_date`, `end_date`는 API 필드만 준비되어 있고 실제 값 제공은 추가 구현이 필요하다.

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

## PostgreSQL 전환 작업 순서

1. 서버에서 PostgreSQL 관리자 비밀번호를 확인한다.
2. `gscert_prod` DB를 생성한다.
3. `gscert_app` 계정을 생성한다.
4. `gscert_app`에 `gscert_prod` 권한을 부여한다.
5. 서버 환경 변수에 DB 접속 정보를 등록한다.
6. `myproject.postgres_settings`로 Django 연결을 확인한다.
7. Django migration을 실행한다.
8. 기존 SQLite 데이터를 PostgreSQL로 이전한다.
9. 기준정보 조회 코드를 PostgreSQL repository로 전환한다.
10. 외부 PC에서 API 조회를 테스트한다.

## 서버 적용 시 주의사항

GitHub에서 코드를 pull하는 것만으로 PostgreSQL 전환이 끝나지는 않는다.

서버에서 추가로 수행해야 하는 작업은 다음과 같다.

- Python 패키지 설치 또는 갱신
- PostgreSQL DB 생성
- PostgreSQL 계정 생성
- 환경 변수 등록
- migration 실행
- 기존 SQLite 데이터 이전
- 서비스 재시작

코드 반영은 `git pull`로 가능하지만, DB 생성과 데이터 이전은 별도 배포 절차로 처리해야 한다.
