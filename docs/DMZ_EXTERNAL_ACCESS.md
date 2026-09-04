# 외부 공개 구성 — DMZ 리버스 프록시 설계 (확정본)

목표: TTA 직원이 사외에서 `https://gsai.tta.or.kr` 로 GSCert 웹앱 전체를 쓸 수 있게 한다.
방식: DMZ PC 1대를 **리버스 프록시 전용**으로 두고, 내부 194 앱서버로 443 한 포트만 통과시킨다.
인증: **회사 구글 계정(Google Workspace `tta.or.kr`) 로그인 전용.**

> 설계 확정: 2026-08-21. 구현은 별도 승인 후 진행.

---

## 1. 확정된 결정

| # | 항목 | 결정 |
|---|------|------|
| A-0 | 외부 사용자 범위 | TTA 직원만 (사외 인원 없음) |
| A-1 | Google Workspace | `tta.or.kr` 사용 중 → ID 토큰 `hd` 클레임 검증 가능 |
| A-2 | 인가 범위 | TTA 전원 (별도 allowlist 없음) |
| A-3 | 계정 생성 | 구글 이메일 `@` 앞부분을 Django username 으로 자동 생성 |
| A-4 | 로컬 비밀번호 | **사용 안 함.** 구글 로그인 전용 (`set_unusable_password()`) |
| A-5 | 세션 | 30일 절대만료 + 활동 시 갱신(rolling) |
| A-6 | `/admin/` | 외부 차단, 사내 직결에서만 접근 |
| B-1 | 도메인 | `gsai.tta.or.kr` 단일 이름 + **split-horizon DNS** |
| B-2 | DMZ 주소 | 공인 IP 배정 |
| B-3 | WAF/IPS | 경계에 **적용되어 있음** → DMZ nginx 차단 규칙은 최소로 |
| B-4 | DMZ 80 포트 | 개방 (HTTPS 308 리다이렉트 전용) |
| B-5 | DMZ OS | Linux |
| C-1 | `/api/local-review/*` | **외부 차단** (사내 전용) |
| C-2 | `/api/server-time/*` | 로그인한 전원 사용 가능 (권한 분리 없음) |
| C-3 | LLM 엔드포인트 | 개방 + 사용자별 rate limit |
| C-4 | 업로드 한도 | 외부 50m (사내 200m 유지) |
| C-5 | 대량 다운로드 | 개방 + 건수 제한 + 감사 로그 |
| D-1 | 전환 정책 | 전환 완료 후 로그인 없이 사용 불가 |
| D-2 | 인증서 | Let's Encrypt DNS-01 (DMZ) |
| D-3 | `SECRET_KEY` 교체 | 로그인 강제 전환과 동시 |
| D-4 | 로그 보존 | 기존 정책 확장 (감사 로그 분리 필요 — 3.5 참고) |
| D-5 | 모니터링 | 4단계 (5장) |
| D-6 | `/consultation/` (8787) | **외부 차단.** 사내 직결에서만 사용 (2.3 참고) |

---

## 2. 아키텍처

### 2.1 트래픽 경로

```
[외부 직원]                                  [사내 직원]
    |                                            |
    | 공개 DNS: gsai.tta.or.kr → DMZ 공인 IP      | 사내 DNS: gsai.tta.or.kr → 210.96.71.194
    v                                            |
[경계 WAF/IPS]                                   |
    v                                            |
[DMZ PC (Linux) — nginx 전용]                    |
  - Let's Encrypt 공인 인증서로 TLS 종단          |
  - /admin/, /api/local-review/ 차단              |
  - rate limit, XFF 정규화                        |
  - 앱/DB/자격증명 없음                            |
    | 443 (자체서명 검증)                          |
    v                                            v
[194 앱서버] -- nginx → Django(127.0.0.1:8000) → PostgreSQL / 파일서버 / ECM
```

**split-horizon DNS 가 필수인 이유**: A-6(admin 사내만), C-1(로컬 점검 앱 사내만),
A-4(비상 superuser 사내만) 는 모두 "사내 트래픽이 DMZ 를 거치지 않음"을 전제로 성립한다.
단일 전환(모두 DMZ 경유)하면 사내 담당자도 admin 과 로컬 점검 앱을 쓸 수 없다.

이 방식의 부수 효과:

- 방화벽 F5(내부 → DMZ 차단) 를 그대로 유지할 수 있다
- DMZ 가 `Host` 를 재작성할 필요가 없다 (그대로 통과)
- `CSRF_TRUSTED_ORIGINS`·센터 라우팅 `BY_HOST` 에 외부 도메인을 추가할 필요가 없다
  (`SERVER_DOMAIN` 별칭으로 이미 등록됨)
- 인증서는 외부(Let's Encrypt)/사내(자체서명, 배포 완료)가 각자 호스트에서 같은 도메인을
  서비스한다. 충돌 없음

**전산팀 요청**: `gsai.tta.or.kr` 을 사내 DNS 에서는 `210.96.71.194`,
공개 DNS 에서는 DMZ 공인 IP 로 해석되도록 분리.

### 2.2 방화벽 정책

| # | 구간 | 프로토콜/포트 | 출발지 | 목적지 | 비고 |
|---|------|--------------|--------|--------|------|
| F1 | Internet → DMZ | TCP 443 | any | DMZ 공인 IP | 유일한 서비스 인바운드 |
| F2 | Internet → DMZ | TCP 80 | any | DMZ 공인 IP | 308 리다이렉트 전용 |
| F3 | DMZ → 내부 | TCP 443 | DMZ | **210.96.71.194 단일 호스트** | 이것만 허용 |
| F4 | DMZ → 내부 | 그 외 전부 | DMZ | 내부 전체 | **차단** (5432·445·139·3389·5985·8000·22) |
| F5 | 내부 → DMZ | 전부 | 내부 | DMZ | **차단** (관리는 관리망/점프박스) |
| F6 | DMZ → Internet | TCP 443 | DMZ | ACME·패키지 저장소 | 최소 허용. 나머지 아웃바운드 차단 |

### 2.3 인증 우회 경로 (Django 를 거치지 않는 location)

전역 로그인 미들웨어는 Django 를 통과하는 요청만 막는다.
[setup/nginx.conf](../setup/nginx.conf) 의 location 4개 중 2개가 우회 경로다.

| location | 처리 주체 | 로그인 미들웨어 적용 | 조치 |
|---|---|---|---|
| `/static/` | nginx alias | 미적용 | 민감 파일 0건 확인 → 그대로 |
| `/ws/` | Django Channels (ASGI) | 미적용 (HTTP 미들웨어 대상 아님) | consumer 에서 직접 검사 |
| `/consultation/` | nginx → 8787 서버 직접 프록시 | 미적용 | **DMZ 에서 차단** (D-6) |
| `/` | Django (http) | 적용 | 미들웨어로 처리 |

**`/ws/` — WebSocket 익명 접속**

[myproject/asgi.py:21](../myproject/asgi.py:21) 에 `AuthMiddlewareStack` 이 있어 `scope["user"]` 는
채워지지만, 두 consumer 가 무조건 `accept()` 한다.

- [main/consumers.py:13](../main/consumers.py:13)
- [playwright_job/consumers.py:286](../playwright_job/consumers.py:286)

→ `connect()` 에서 `scope["user"].is_authenticated` 확인 후 아니면 `close(4401)`.

**`/consultation/` — 8787 상담 앱 → 외부 차단 확정 (D-6)**

[setup/nginx.conf:62](../setup/nginx.conf:62) 에서 nginx 가 Django 를 건너뛰고 8787
(`210.96.71.67:8787`) 로 직접 프록시한다. 우리 로그인·`hd` 검증·감사 로그가 적용되지 않으므로
DMZ 에서 404 로 차단한다.

사내 사용자는 사내 DNS 로 194 에 직결되므로 **현재 사용자에게 영향이 없다.**
외부에서만 보이지 않게 되는 것이며, 추후 8787 팀과 협의해 개방하려면 DMZ 설정의
`location ^~ /consultation/` 블록만 제거하면 된다. 8787 팀에 별도 통보할 사항은 없다.

### 2.4 클라이언트 IP 신뢰 (X-Forwarded-For)

`X-Forwarded-For` 는 클라이언트가 임의로 채워 보낼 수 있는 평범한 HTTP 헤더다.
현재 194 nginx 는 `$proxy_add_x_forwarded_for` 로 **클라이언트가 보낸 값을 지우지 않고 append**
하며, Django 는 맨 왼쪽을 취한다 → 위조값이 채택된다.

XFF 왼쪽 값이 쓰이는 곳:

| 위치 | 쓰임 | 위조 시 결과 |
|---|---|---|
| [main/views/init.py:48](../main/views/init.py:48) | 센터 기본값 선택 | 낮음 |
| [main/request_logging.py:125](../main/request_logging.py:125) | 전체 접근/에러 로그 `ip=` | **감사 로그 오염** |
| [ecm_download_review_api.py:242](../main/views/review/ecm_download_review_api.py:242) | 작업 생성자 `request_ip` | 작업 이력 위조 |
| [ecm_download_review_api.py:473](../main/views/review/ecm_download_review_api.py:473) | 수동 통과 `requested_by` | **판정 책임자 기록 위조** |

`_client_ip()` 가 세 파일에 중복 구현되어 있으므로, 각 뷰를 고치는 대신 nginx 계층에서 해결한다.

```nginx
# DMZ nginx — append 가 아니라 덮어쓰기 (클라이언트가 보낸 값 폐기)
proxy_set_header X-Forwarded-For $remote_addr;
```

```nginx
# 194 nginx — 신뢰된 프록시만 벗겨 $remote_addr 를 진짜 클라이언트 IP 로 만든다
set_real_ip_from  <DMZ PC IP>;
real_ip_header    X-Forwarded-For;
real_ip_recursive on;
```

부수 효과: [server_time_control_api.py:34](../main/views/review/server_time_control_api.py:34) 는
`REMOTE_ADDR` 을 쓰는데 프록시 뒤라 **항상 `127.0.0.1`** 로 기록된다. realip 도입으로 함께 해결된다.

다만 로그인 강제 후 감사의 1차 근거는 IP 가 아니라 **로그인 사용자**여야 한다.
`requested_by` 를 사용자명으로 바꾸는 것이 근본 해결이고 realip 는 보조다.

### 2.5 센터 라우팅

판정 순서 ([main/views/init.py:48](../main/views/init.py:48)):

1. `default_center_for_client_ip()` — `210.96.0.0/16` → 상암, `210.104.0.0/16` → 분당
2. miss 면 `default_center_for_host()` — 현재 `MAIN_SERVER_IP` → 분당

외부 사용자 IP 는 두 대역에 없어 2번으로 떨어진다. **2번 기본값을 상암으로 변경한다.**
사내는 1번이 먼저 걸리므로 분당 직원(210.104)·상암/영남(210.96) 동작은 변하지 않는다.
[main/tests.py:1471](../main/tests.py:1471) 부근의 기본값 검증 테스트를 함께 수정해야 한다.

---

## 3. 인증 설계

### 3.1 회사 계정 판별

Google OIDC ID 토큰의 `hd`(hosted domain) 클레임으로 판별한다.

| 계정 종류 | `email` | `hd` |
|---|---|---|
| Google Workspace (회사) | `hong@tta.or.kr` | `"tta.or.kr"` |
| 일반 구글 계정 | `hong@gmail.com` | 없음 |
| **회사 이메일로 만든 개인 구글 계정** | `hong@tta.or.kr` | **없음** |

3행 때문에 `email.endswith("@tta.or.kr")` 검사는 부적합하다. **`hd == "tta.or.kr"` 이 올바른 검사다.**

함께 검증할 항목:

- `hd == "tta.or.kr"`
- `email_verified == true`
- `aud == 우리 client_id` (다른 앱 토큰 재사용 차단)
- `iss` 가 `accounts.google.com` 또는 `https://accounts.google.com`
- JWKS 서명 검증 + `exp`

인증 요청의 `hd=tta.or.kr` 파라미터는 **계정 선택 화면을 걸러주는 UX 장치일 뿐 보안 통제가 아니다.**
서버에서 위 재검증이 반드시 있어야 한다.

### 3.2 계정 프로비저닝

- 첫 구글 로그인 시 Django 계정 자동 생성
- username = 구글 이메일 `@` 앞부분
- **비밀번호 없음** (`set_unusable_password()`) → 로컬 비밀번호 로그인 경로 비활성화
- 이메일 전체를 별도 필드로 보관 (실제 식별자). username 충돌 시 뒤에 숫자 부여

**로컬 비밀번호를 열어두면 안 되는 이유**: 초기 비밀번호를 ID 와 같게 두면 공격자가 구글을
거치지 않고 `username=hong / password=hong` 으로 로그인할 수 있다. A-2 가 "TTA 전원"이라
계정이 계속 늘어나므로 "아직 안 바꾼 계정"이 상시 존재한다.

**비상 접근**: superuser 1개만 강한 비밀번호로 유지하고, DMZ 에서 비밀번호 로그인 경로를
차단해 사내 직결로만 사용한다.

### 3.3 전역 인증

47개 라우트에 데코레이터를 개별 부착하면 누락이 생긴다. 미들웨어로 기본 차단 + 화이트리스트.

```python
# main/require_login.py (신규)
LOGIN_EXEMPT_PREFIXES = ('/accounts/login/', '/accounts/logout/', '/oauth/', '/static/', '/healthz')
```

`MIDDLEWARE` 에서 `AuthenticationMiddleware` **뒤에** 배치.
`/api/local-review/*` 는 브라우저 세션이 없으므로 토큰 인증 경로로 예외 처리하고,
DMZ 에서 외부 차단한다(C-1).

### 3.4 세션

- `SESSION_COOKIE_AGE` = 30일, `SESSION_SAVE_EVERY_REQUEST = True` (활동 시 갱신)
- `SESSION_COOKIE_SECURE = True`, `SESSION_COOKIE_HTTPONLY = True`, `CSRF_COOKIE_SECURE = True`

30일 절대만료를 두는 이유: 구글은 로그인 시점에만 개입하므로, 퇴사자 구글 계정을 정지시켜도
이미 발급된 Django 세션은 만료가 없으면 영구히 유효하다.

### 3.5 감사 로그

[log_retention.ps1](../log_retention.ps1) 은 **재시작 로그 5쌍만** 남긴다 — 날짜 기준이 아니라
**재시작 횟수 기준**이므로 서버를 다섯 번 재시작하면 이전 기록이 사라진다. 감사용으로 쓸 수 없다.

→ 감사 대상 이벤트를 애플리케이션 재시작 로그와 **분리**해 날짜 기준(예: 1년) 보존:
로그인/로그아웃, `manual-pass`, `bulk-download`, `full-documents-download`,
`server-time` 변경, 신규 계정 생성.

---

## 4. 작업 순서

1. **전산팀 요청** — 메일 초안: [DMZ_REQUEST_FOR_IT_TEAM.md](DMZ_REQUEST_FOR_IT_TEAM.md)
   - DMZ 세그먼트 + 공인 IP 1개 배정
   - split-horizon DNS (`gsai.tta.or.kr`: 사내 → 194, 공개 → DMZ)
   - 방화벽 F1~F6
   - 신규 DMZ 호스트를 WAF/IPS 보호 대상에 포함 (적용 확인됨)
   - **ACME DNS-01 위임** — `_acme-challenge.gsai.tta.or.kr` CNAME 위임 또는 DNS API 권한.
     받지 못하면 60일마다 TXT 레코드 수동 등록을 요청해야 하고, 한 번 놓치면 인증서 만료로
     서비스가 중단된다
   - **DMZ 서버 관리 접근 경로** — F5(내부 → DMZ 차단) 때문에 사내에서 직접 붙을 수 없다.
     기존 관리망/점프박스 표준 경로 확인
2. **194 노출면 축소** — runserver `127.0.0.1` 바인딩 + 운영 ASGI 서버로 교체,
   PostgreSQL `listen_addresses`·`pg_hba.conf` 내부 제한 및 중복 인바운드 규칙 정리,
   Windows 방화벽 Public/Private 프로필 활성화, DestinyECMAgent·WinRM·SMB 내부 대역 제한
3. **앱 구현** (아래 목록)
4. **사내에서 로그인 강제 선행 운영** — 외부 개방 전에 사내에서 먼저 돌려 회귀를 잡는다
5. **DMZ PC 구축** — Linux 최소 설치, nginx 만, Let's Encrypt DNS-01,
   [setup/nginx-dmz.conf.example](../setup/nginx-dmz.conf.example) 적용
6. **방화벽 개방 + DNS 전환**
7. **검증** (6장)

### 구현 목록

| # | 내용 | 근거 |
|---|------|------|
| E1 | Google OIDC 로그인 + `hd` 검증 + 자동 프로비저닝, 로컬 비밀번호 비활성화 | 3.1, 3.2 |
| E2 | 전역 인증 미들웨어 + `/welcome/` 라우트 누락 수정 | 3.3 |
| E3 | WebSocket consumer 인증 검사 (`close(4401)`) | 2.3 |
| E4 | 센터 기본값 상암 + 관련 테스트 수정 | 2.5 |
| E5 | realip 기반 클라이언트 IP 신뢰 + `requested_by` 를 사용자명으로 | 2.4 |
| E6 | `DEBUG=False`, `SECRET_KEY` 환경변수화 및 신규 발급 | D-3 |
| E7 | 세션·쿠키 보안 설정 | 3.4 |
| E8 | 감사 로그 분리 + 날짜 기준 보존 | 3.5 |
| E9 | LLM·업로드·대량 다운로드 rate limit / 한도 | C-3~5 |

> **`/welcome/` 라우트 누락**: `LOGIN_REDIRECT_URL = '/welcome/'`
> ([myproject/settings.py:404](../myproject/settings.py:404)) 인데 `main/urls.py` 에 `path` 가 없다.
> `welcome` 뷰([main/views/init.py:14](../main/views/init.py:14))는 존재한다.
> 지금은 로그인을 아무도 쓰지 않아 드러나지 않았고, 로그인 강제 시 즉시 404 가 된다.

> **`SECRET_KEY`** ([myproject/settings.py:25](../myproject/settings.py:25)): TLS 인증서와 무관한
> Django 내부 서명 키다. 세션 쿠키 서명에 쓰이므로 이 값을 아는 사람은 구글 로그인을 거치지
> 않고 세션을 위조할 수 있다. 현재 `django-insecure-…` 기본값이 git 에 커밋되어 있어
> **새 값 발급이 필수**(히스토리에 남아 삭제로는 해결되지 않는다). 교체 시 전체 세션이
> 무효화되므로 로그인 강제 전환과 같은 시점에 진행한다.

---

## 5. 모니터링

**1단계 — 자동 차단 (사람 개입 없음)**

DMZ(Linux)에 fail2ban: 로그인 실패 반복 IP 자동 차단. 경계 WAF/IPS 와 계층이 다르다.

**2단계 — 자동 알림 (즉시 알아야 하는 것만)**

- 로그인 실패 급증 (10분간 20회 이상)
- 5xx 급증 (앱 장애)
- **Let's Encrypt 자동 갱신 실패** — 놓치면 90일 후 전체 서비스가 인증서 만료로 멈춘다
- `/api/server-time/action/` 호출 (C-2 로 전원 허용했으므로 알림으로 보완)

**3단계 — 주 1회 확인 (10분)**

- 외부 IP 별 접속 통계 (낯선 대역, 비정상 시간대)
- `manual-pass` / `bulk-download` 실행 목록
- 신규 생성 계정 목록 (자동 프로비저닝이므로 예상 밖 계정 확인)

**4단계 — 로그 보존**

3.5 참고. 감사 로그를 재시작 로그와 분리해 날짜 기준 보존.

---

## 6. 검증

```powershell
# 외부 회선 — 열려야 하는 것
curl.exe -s -o NUL -w "%{http_code}" https://gsai.tta.or.kr/           # 302 → 구글 로그인
curl.exe -s -o NUL -w "%{http_code}" https://gsai.tta.or.kr/history/   # 302 (200 이면 인증 실패)

# 외부 회선 — 막혀야 하는 것
curl.exe -s -o NUL -w "%{http_code}" https://gsai.tta.or.kr/admin/                    # 404
curl.exe -s -o NUL -w "%{http_code}" https://gsai.tta.or.kr/api/local-review/health/  # 404
curl.exe --max-time 5 http://gsai.tta.or.kr:8000/                                     # timeout
curl.exe --max-time 5 telnet://gsai.tta.or.kr:5432                                    # timeout

# 사내 — DMZ 를 거치지 않고 194 로 직결되는지
Resolve-DnsName gsai.tta.or.kr    # 210.96.71.194 여야 함
curl.exe -k -s -o NUL -w "%{http_code}" https://gsai.tta.or.kr/admin/   # 302 (로그인 화면)

# DMZ PC 에서 — 내부로 443 외에는 못 나가야 한다
Test-NetConnection 210.96.71.194 -Port 443    # 성공
Test-NetConnection 210.96.71.194 -Port 5432   # 실패
Test-NetConnection 210.96.71.194 -Port 445    # 실패
Test-NetConnection 210.96.71.194 -Port 3389   # 실패
```

**인증 우회 확인** (로그아웃 상태로 외부에서):
`/api/jobs/`, `/api/server-time/action/`, `/history/report/<시험번호>/download/`,
`/api/projects/bulk-download/` 가 전부 로그인 요구로 막히는지.
WebSocket 은 `wscat -c wss://gsai.tta.or.kr/ws/status/test/` 로 4401 종료를 확인한다.
