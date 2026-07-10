# 상담(consultation) 앱 리버스 프록시 — 194 측 설정 및 도메인 교체 가이드

우리(194) nginx가 `https://210.96.71.194.nip.io/consultation/` 로 8787 상담 앱을 리버스 프록시한다.
8787 앱은 구글 로그인(OAuth) 을 쓰며, 구글이 **IP redirect_uri 를 거부**하므로 상담은 반드시
**도메인**으로 서비스해야 한다. 지금은 무료·무설정 와일드카드 DNS 인 **nip.io** 를 쓰고,
추후 회사 도메인 **`aisa.tta.or.kr`** 로 교체할 수 있게 구성돼 있다.

---

## 1. 현재 구성 (nip.io)

- 접속 주소: **`https://210.96.71.194.nip.io/consultation/`**
- 접두어(prefix): `/consultation` — 8787 앱의 `CONSULT_BASE_PREFIX` 와 동일해야 함
- OAuth 콜백: `https://210.96.71.194.nip.io/consultation/auth/callback`

### 호스트별 역할 분리 (중요)
메인 GSCert 앱은 Django 가 **Host(`request.get_host`) 기반으로 센터(상암/영남/분당)를 라우팅**한다
(`myproject/settings.py` 의 `DOWNLOAD_REVIEW_*_BY_HOST`, `main/context_processors.py` 의 `nav_home_url`).
따라서 호스트를 아래처럼 분리한다.

| Host | 서비스 | nginx 정책 |
|------|--------|-----------|
| `210.96.71.194` (IP) | 메인 GSCert 앱 | 그대로 IP로 서비스. `/consultation/` 로 오면 도메인으로 302 |
| `210.96.71.194.nip.io` (도메인) | 상담 앱(8787) | `/consultation/` 프록시. 그 외 경로는 IP로 302(센터 라우팅 보호) |

- 리다이렉트는 **302(임시)** — 향후 도메인 교체 시 브라우저 캐시에 고정되지 않도록.
- 메인 앱을 절대 도메인으로 서비스하지 말 것(센터 라우팅·네비홈이 깨짐).

---

## 2. 194 측에서 만진 파일

| 파일 | 내용 |
|------|------|
| `setup/nginx.conf` (템플릿) | 443 서버에 `location /consultation/`(프록시+IP→도메인 302), `location /`(도메인→IP 302), `server_name __SERVER_IP__ __SERVER_DOMAIN__` |
| `setup.ps1` | `$serverDomain = "$serverIP.nip.io"` 정의 후 `__SERVER_DOMAIN__` 치환 |
| `setup/gen_self_signed_cert.ps1` | `-ServerDomain` 파라미터 추가, 인증서 SAN 에 `IP:<ip>,DNS:<domain>` 동시 등록, CN=도메인 |
| `C:\nginx-1.29.8\conf\nginx.conf` (실서버, git 미포함) | 위 템플릿을 리터럴 값으로 반영 |

> 실서버 `nginx.conf` 는 템플릿에서 생성되는 산출물이다. 값이 꼬이면
> `setup.ps1` 재실행(또는 템플릿을 손으로 치환)해서 다시 만들면 된다.

---

## 3. 인증서 (자체서명 + 사내 루트 신뢰)

nip.io 로 접속하려면 인증서 SAN 에 도메인이 있어야 브라우저 이름-불일치 경고가 안 뜬다.
갱신 명령(도메인 바뀌면 `-ServerDomain` 만 교체):

```powershell
powershell -ExecutionPolicy Bypass -File C:\Claude_GSCert\setup\gen_self_signed_cert.ps1 `
  -ServerIp 210.96.71.194 -ServerDomain 210.96.71.194.nip.io
# 생성 후: nginx.exe -t  &&  nginx.exe -s reload
```

- 인증서를 재생성하면 지문이 바뀌므로, 기존에 `gscert.crt` 를 "신뢰할 수 있는 루트 인증 기관"에
  등록해둔 **사내 PC들에 새 gscert.crt 를 재배포**해야 경고가 완전히 사라진다(1회 작업, GPO/certlm.msc).
- nip.io 는 Let's Encrypt 공인 인증서 발급이 사실상 제한되므로 사내에선 자체서명이 정답.
- `aisa.tta.or.kr` 처럼 **회사 소유 공인 도메인**으로 가면, 공개 DNS 통제 시 Let's Encrypt(DNS-01)
  로 **무경고 공인 인증서**도 가능(자체서명 재배포 불필요).

---

## 4. 향후 도메인 교체 절차 — `aisa.tta.or.kr` 로 이전

접두어(`/consultation`)는 그대로 두고 **도메인 문자열만** 바꾸면 된다. 바꿀 곳은 딱 5군데:

| # | 위치 | 현재(nip.io) | 교체 후(예시) | 담당 |
|---|------|-------------|--------------|------|
| 1 | TTA DNS A레코드 | (nip.io 자동) | `aisa.tta.or.kr → 210.96.71.194` | TTA 전산팀 |
| 2 | nginx `__SERVER_DOMAIN__` (setup.ps1 `$serverDomain`) | `<ip>.nip.io` | `aisa.tta.or.kr` | 우리 |
| 3 | 자체서명 인증서 SAN (gen_self_signed_cert.ps1 `-ServerDomain`) | `<ip>.nip.io` | `aisa.tta.or.kr` | 우리 |
| 4 | 구글 콘솔 승인된 리디렉션 URI | `.../nip.io/consultation/auth/callback` | `https://aisa.tta.or.kr/consultation/auth/callback` | 우리/8787 |
| 5 | 8787 `auth.redirect_uri` | `.../nip.io/...` | `https://aisa.tta.or.kr/consultation/auth/callback` | 8787 |

절차:
1. TTA 전산팀에 `aisa.tta.or.kr → 210.96.71.194` A레코드 등록 요청(사내 DNS만으로도 사내 접속 충분).
2. 우리: `setup.ps1` 의 `$serverDomain` 을 `aisa.tta.or.kr` 로 바꿔 재실행(또는 실서버 `nginx.conf`
   의 `210.96.71.194.nip.io` 를 `aisa.tta.or.kr` 로 일괄 치환) → `nginx -t && nginx -s reload`.
3. 우리: 인증서 재생성 `-ServerDomain aisa.tta.or.kr` (공인 인증서 발급이 가능하면 그쪽 권장).
4. 우리/8787: 구글 콘솔 리디렉션 URI 에 새 도메인 콜백 **추가**(기존 값은 이전 안정화까지 병행 유지 후 제거).
5. 8787: `auth.redirect_uri` 새 도메인으로 변경 후 앱 재시작.
6. 확인: `https://aisa.tta.or.kr/consultation/` 접속 → 로그인 → 자료조회.

> 접두어 `CONSULT_BASE_PREFIX=/consultation` 는 도메인 교체와 무관하게 **그대로** 둔다.
> IP 로 상담에 접속하면 nginx 가 자동으로 새 도메인으로 302 시키므로 사용자 혼선이 없다.

---

## 5. 검증 명령 (현재 nip.io 기준)

```powershell
# IP 상담 접속 → 도메인으로 302 되는지
curl.exe -k -s -o NUL -w "%{http_code} -> %{redirect_url}`n" https://210.96.71.194/consultation/
# 도메인 상담 → 8787 프록시(200/401)
curl.exe -k -s -o NUL -w "%{http_code}`n" https://210.96.71.194.nip.io/consultation/
# 도메인으로 메인앱 접속 → IP로 302(센터 라우팅 보호)
curl.exe -k -s -o NUL -w "%{http_code} -> %{redirect_url}`n" https://210.96.71.194.nip.io/
```
