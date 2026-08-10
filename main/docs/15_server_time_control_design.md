# 서버 시간 임시 변경 설계

## 목적과 범위

`/download-review/`에서 실제 시각 변경 대상 서버(상암·영남 ECM 원문 시스템, `210.96.71.85`)의 날짜와 시간을
임시로 과거 시각으로 변경하고, 3분 뒤 정상 시각으로 복구한다.

- 웹 UI/lease 상태(revision)/3분 타이머/PIN 인증은 194(`210.96.71.194`, GSCert 앱 서버)가 관리한다.
- 실제 OS 시각 변경·W32Time 제어·NTP 재동기화는 85(`210.96.71.85`)에서 일어난다. 194는 이 작업을
  WinRM(`pywinrm`, NTLM 인증)으로 85에 원격 실행한다 — 194 자신의 시각은 바뀌지 않는다.
- 85 접속 계정(`gsai`)은 85의 로컬 Administrators 그룹 멤버이며, 워크그룹 환경의 UAC 원격 토큰
  필터링을 끄기 위해 85에 `LocalAccountTokenFilterPolicy=1`을 설정했다(KB951016).
- 자격증명은 194의 Machine 환경변수(`SERVER_TIME_REMOTE_USER`/`SERVER_TIME_REMOTE_PASSWORD`)로만
  주입한다(`ECM_USERNAME`/`ECM_PASSWORD`와 동일한 패턴) — 코드/DB에는 절대 저장하지 않는다.
- 운영체제는 두 서버 모두 Windows Server 2022 Standard다.
- 직원 전용 내부망 기능으로 운영하며 별도 로그인/권한 검사는 두지 않는다.
- 시간대는 `Korea Standard Time`(`Asia/Seoul`, UTC+09:00)으로 고정한다.
- 미래 시각은 허용하지 않는다. 이 판정은 이미 변경된 OS 시각이 아니라 정상 시간 원본에서 계산한 현재 시각을 기준으로 한다.
- 초 단위 입력은 받지 않고 분 단위로 설정한다.
- 과거 날짜에 업무상 하한은 두지 않되, Windows와 사용 라이브러리가 표현할 수 없는 값은 서버에서 거부한다.
- 기존 download-review `20:00-07:00` 작업 시작 제한은 복구하지 않고 폐기한다.

## 사용자 흐름

1. `서버 시간 설정` 버튼을 누르면 서버가 읽은 현재 날짜와 시각을 팝업에 표시한다.
2. 팝업을 연 응답에는 현재 상태와 원자적 갱신에 사용할 `revision`을 포함한다.
3. 사용자는 이름, 숫자 4자리 PIN, 변경할 과거 날짜·시각을 입력한다.
4. 서버는 `idle` 상태와 `revision` 일치를 한 번에 검사한다. 먼저 성공한 요청만 시간을 변경한다.
5. 변경 중에는 작업자 이름, 설정된 시각, 정상 복구 예정까지의 남은 시간을 모든 사용자에게 표시한다. PIN은 표시하거나 응답하지 않는다.
6. 최초 변경으로부터 단조 증가 시계 기준 3분 뒤 정상 시각으로 자동 복구한다.
7. 변경한 사용자는 같은 이름과 PIN을 입력해 조기 복구하거나 다른 과거 시각으로 재설정할 수 있다.
8. 재설정에 성공하면 그 시점부터 3분을 다시 계산한다.
9. 이름/PIN이 다르거나 revision이 오래된 요청은 거부한다.
10. 잠금은 3분 경과가 아니라 정상 시각 복구와 검증이 성공한 뒤 해제한다.
11. 시간 변경·복구 중 접수된 ECM 제출물 자동 점검 작업은 `queued` 상태로 유지하고, 정상 시각 복구 검증 후 워커가 순서대로 시작한다.

## PIN 처리

- PIN은 정확히 숫자 4자리로 제한한다.
- 평문 PIN은 DB, 로그, API 응답에 저장하지 않는다.
- 임의 salt를 사용한 Django 비밀번호 해시 형식으로 현재 lease 동안만 보관한다.
- 이름 비교는 앞뒤 공백을 제거한 확정 문자열을 사용한다.
- PIN 실패 횟수와 요청 속도를 제한한다. 4자리 PIN은 최대 10,000개뿐이므로 제한 없이 재시도하게 두면 안 된다.
- lease가 정상 종료되면 PIN 해시는 제거한다.
- 이름과 PIN은 로그인 인증이 아니라 해당 시간변경 lease의 제어권을 확인하는 수단이다.

## 상태와 복구 원칙

상태는 `idle`, `changing`, `active`, `restoring`, `recovery_failed`로 구분한다.

- Django 웹 프로세스에는 OS 시간 변경 권한을 주지 않는다.
- 관리자 권한의 별도 Windows 서비스가 실제 시간 변경, 단조 증가 타이머, 복구를 담당한다.
- 브라우저 종료나 Django 재시작은 복구 타이머에 영향을 주지 않아야 한다.
- 서비스 재시작 또는 서버 재부팅 시 미완료 lease가 있으면 정상 시간 복구를 우선 시도한다.
- 정상 복구는 194 서버의 실제 시간 원본을 확인한 뒤 `w32tm /resync` 또는 확정된 사내 시간 원본을 사용한다.
- 복구 후 시간 원본과의 차이가 허용 오차 안인지 검증한다.
- 복구 실패 시 `recovery_failed` 잠금을 유지하고 운영자가 상태를 볼 수 있게 한다.
- 감사 이력에는 이벤트 순번, 작업자 이름, 요청 IP, 변경 전 시각, 설정 시각, 조기 복구/재설정 여부, 복구 결과를 기록한다.
- OS 시각 변경으로 로그 시간이 역행할 수 있으므로 이벤트 순번과 정상 기준시각 추정값을 별도로 기록한다.

## 구현 전 필수 확인

아래 항목만 우선 확인한다. 결과는 관리자 PowerShell에서 수집한다.

### 194 서버 확인 결과 (2026-08-06)

- Windows Server 2022 Standard 물리 서버이며 AD 도메인에 가입하지 않은 WORKGROUP standalone 서버다.
- 시간 원본은 `time.windows.com,0x8`이고 W32Time은 `Running / Automatic`이다.
- Windows Time 관련 도메인/로컬 강제 정책은 없다.
- 사내 NTP는 없으며 정상 복구 원본은 현재 사용 중인 `time.windows.com`으로 확정한다.
- PostgreSQL reference 연결은 SSL을 사용하지 않고, libpq 클라이언트 인증서 환경변수도 없다.
- `\\210.96.71.99\ecm` 공유는 접근 가능하고 저장 자격증명을 사용한다. 도메인/Kerberos 연결은 아니다.
- 시간 변경 전 W32Time을 중지하고, 복구 후 `Automatic / Running` 상태로 되돌린 다음 강제 재동기화와 오차 검증을 수행한다.
- 외부 NTP가 일시적으로 불가능한 경우를 위해 변경 직전 정상 UTC와 단조 증가 시각을 저장하고, 같은 부팅 세션에서는 `정상 UTC + 단조 경과시간`을 1차 복구값으로 사용할 수 있어야 한다.
- 서버가 재부팅되면 단조 기준이 끊기므로 미완료 lease는 `time.windows.com` 재동기화를 우선하고, 실패하면 `recovery_failed` 잠금을 유지한다.

### 1. 도메인과 시간 원본

```powershell
$computer = Get-CimInstance Win32_ComputerSystem
$computer | Select-Object Name, Domain, PartOfDomain, DomainRole
w32tm /query /source
w32tm /query /status
w32tm /query /configuration
Get-Service W32Time | Select-Object Name, Status, StartType
```

- `PartOfDomain=True`면 AD 도메인 가입 서버다.
- `Source`가 도메인 컨트롤러면 5분 이상 시간 차이에서 Kerberos 문제가 생길 수 있다.
- `Source`가 `Local CMOS Clock`이면 정상 복구에 사용할 별도 시간 원본을 확정해야 한다.

### 2. 그룹 정책 적용 여부

```powershell
gpresult /scope computer /h C:\Windows\Temp\gscert-time-gpo.html
Get-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\W32Time\*' -ErrorAction SilentlyContinue
```

생성된 보고서에서 `Windows Time Service`, `Time Providers`, `NtpClient`를 검색한다. 정책이 있으면 서비스가 임의로 시간을 되돌리거나 로컬 설정을 덮어쓸 수 있다.

### 3. 사내 시간 원본과 접근성

먼저 `w32tm /query /source`와 `/configuration`의 `NtpServer` 값을 시간 원본 후보로 사용한다. 후보가 확인되면 다음을 실행한다.

```powershell
w32tm /stripchart /computer:<시간서버주소> /dataonly /samples:5
Test-NetConnection <시간서버주소> -Port 123 -InformationLevel Detailed
```

NTP는 UDP 123을 사용하므로 `Test-NetConnection -Port 123` 결과만으로 최종 판단하지 않는다. `stripchart`가 실제 시간 샘플을 받는지가 더 중요하다.

### 4. PostgreSQL SSL과 인증 방식

현재 Django 설정에는 PostgreSQL `OPTIONS/sslmode`가 없으므로 코드 기본값만 보면 SSL 강제 설정은 없다. 운영 환경변수나 PostgreSQL 서버 정책은 별도로 확인한다.

194 서버의 프로젝트 가상환경에서 다음을 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py shell --settings=myproject.settings -c "from django.db import connections; c=connections['reference']; c.ensure_connection(); cur=c.cursor(); cur.execute('select ssl, version, cipher from pg_stat_ssl where pid = pg_backend_pid()'); print(cur.fetchone())"
```

- 첫 번째 값이 `True`면 현재 PostgreSQL 연결은 SSL이다.
- `False`면 비암호화 연결이다.
- 접속 비밀번호나 전체 환경변수는 화면에 출력하지 않는다.
- 현재 Django 설정에는 클라이언트 인증서 경로(`sslcert`, `sslkey`)가 정의되어 있지 않다. 운영에서 별도 libpq 환경변수를 쓰는지는 `PGSSLCERT`, `PGSSLKEY`, `PGSSLROOTCERT`, `PGSSLMODE`의 존재 여부만 확인한다.

```powershell
'PGSSLMODE','PGSSLCERT','PGSSLKEY','PGSSLROOTCERT' | ForEach-Object {
    [pscustomobject]@{ Name = $_; Configured = [bool][Environment]::GetEnvironmentVariable($_, 'Machine') }
}
```

### 5. 재부팅 자동 복구 기반

복구 서비스는 아직 구현 전이므로 지금 확인할 자동 시작 서비스는 없다. 구현 후 다음 기준을 검증한다.

```powershell
Get-Service GSCertTimeControl | Select-Object Name, Status, StartType
sc.exe qc GSCertTimeControl
```

- 시작 유형 `Automatic`
- 서비스 계정에 시스템 시간 변경 권한 부여
- 비정상 종료 후 자동 재시작 설정
- 부팅 시 미완료 lease를 감지하고 정상 시간 복구

## 저장소에서 이미 확인된 연결

- ECM은 HTTP 주소를 사용하므로 ECM 연결 자체에는 TLS 서버 인증서 유효기간 문제가 없다.
- PostgreSQL은 `REFERENCE_PG_HOST`의 5432 포트를 사용하며 코드에 `sslmode`가 명시되어 있지 않다.
- 산출물 저장 경로는 기본적으로 `\\210.96.71.99\ecm` SMB 공유다. 194 서버가 도메인 계정으로 이 공유에 접속한다면 시간 변경 시 Kerberos/SMB 인증 영향을 반드시 실측해야 한다.
- 웹 진입점에는 nginx HTTPS 구성이 있으므로 서버 시간 변경 중 HTTP 헤더, CSRF 쿠키 만료, 로그 시각 역행을 시험한다.

## 다음 단계 진입 조건

필수 환경 진단은 완료됐다. 구현 후 실제 194 서버에서 다음을 검증한다.

1. 과거 시각 설정 후 W32Time이 3분 전에 임의 복구하지 않는지.
2. 자동/조기 복구 후 `time.windows.com`과 허용 오차 안으로 동기화되는지.
3. 시간 변경 중과 복구 후 `\\210.96.71.99\ecm` 접근이 유지되는지.
4. 서버 재부팅 시 미완료 lease를 감지하고 즉시 복구하는지.

## 구현 상태

- `GET /api/server-time/`: 서버 시각, lease 상태, revision, 설정자, 남은 시간 조회.
- `POST /api/server-time/action/`: 최초 변경, 같은 이름/PIN 재설정, 조기 복구 요청.
- workflow DB의 `server_time_control`, `server_time_audit`: 원자적 lease와 감사 이력.
- `run_server_time_agent`: 단조 3분 타이머·lease 상태는 194에서 관리하고, W32Time 중지/시작, 시스템
  시각 변경, `w32tm /resync`는 WinRM으로 85에 원격 실행한다. NTP 조회(정상 기준시각)는 194에서
  직접 하고, 복구 검증은 85 자신의 시각(`Get-Date` 원격 조회)을 그 NTP 값과 비교한다.
- `GSCertTimeControl` Windows 서비스와 설치 스크립트: 194에서 자동 시작과 실패 시 재시작(85에는
  아무 서비스도 설치하지 않음, WinRM만 켜져 있으면 됨).
- `/download-review/`의 서버 시간 설정 팝업: 이름, 4자리 PIN, 과거 분 단위 시각, 설정자·남은 시간 표시.
- 기존 download-review 시간 제한은 제거했고 새 작업은 즉시 queued 처리한다. 단, 서버 시간이 정상 상태가 아니면 워커가 claim하지 않고 원상복구까지 대기열에 유지한다.

개발 PC에서는 dry-run으로 설정/충돌/PIN 거부/조기 복구와 UI를 검증했다. WinRM 연결(인증, 85 시각
조회, W32Time 상태 조회)은 194→85 실제 통신으로 확인했다. 실제 OS 시간 변경·자동 복구·재부팅 복구는
아직 85에서 실행해보지 않았다 — 85는 실사용 ECM 시스템이라 실제 시각 변경 테스트는 별도 확인 후 진행한다.
