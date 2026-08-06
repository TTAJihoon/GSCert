# 상담(consultation) 앱 리버스 프록시 — 194 측 설정 및 도메인 교체 가이드

우리(194) nginx가 `https://gsai.tta.or.kr/consultation/` 로 8787 상담 앱을 리버스 프록시한다.
8787 앱은 구글 로그인(OAuth) 을 쓰며, 구글이 **IP redirect_uri 를 거부**하므로 상담은 반드시
**도메인**으로 서비스해야 한다.

> (2026-08 갱신) 전산팀이 정식 도메인 **`gsai.tta.or.kr`** 을 194 서버 IP(`210.96.71.194`)로
> 직접 DNS A레코드 등록을 완료했다(Cloudflare Tunnel 은 검토했지만 채택하지 않음 — DNS가
> Cloudflare 프록시가 아니라 194 IP를 직접 가리키므로, cloudflared 없이 기존 nginx+자체서명
> 인증서 구조 그대로 도메인을 서비스한다). 이에 따라 임시로 쓰던 무료 와일드카드 DNS
> **nip.io** 와 **IP 단독 접속** 을 폐기하고 `gsai.tta.or.kr` 하나로 통합했다.
> `setup/cloudflared-config.yml`, `setup/install_cloudflared.ps1` 은 검토 당시 준비했던
> 미사용 참고 파일이다(직접 DNS 방식을 쓰므로 적용하지 않음).

---

## 1. 현재 구성 (gsai.tta.or.kr)

- 접속 주소: **`https://gsai.tta.or.kr/consultation/`**
- 접두어(prefix): `/consultation` — 8787 앱의 `CONSULT_BASE_PREFIX` 와 동일해야 함
- OAuth 콜백: `https://gsai.tta.or.kr/consultation/auth/callback`
- 8787 팀에 전달할 내용은 [CONSULTATION_DOMAIN_CUTOVER_FOR_8787_TEAM.md](CONSULTATION_DOMAIN_CUTOVER_FOR_8787_TEAM.md) 참고.

### 호스트별 역할 분리
메인 GSCert 앱은 Django 가 **Host(`request.get_host`) 기반으로 센터(상암/영남/분당)를 라우팅**한다
(`myproject/settings.py` 의 `DOWNLOAD_REVIEW_*_BY_HOST`, `main/context_processors.py` 의 `nav_home_url`).
`SERVER_DOMAIN` 환경변수(=`gsai.tta.or.kr`)를 설정하면 이 매핑에 도메인이 `MAIN_SERVER_IP`의
별칭으로 자동 등록되어, 메인 앱도 IP와 도메인 양쪽에서 센터 라우팅·네비홈이 깨지지 않고 동작한다.

| Host | 서비스 | nginx 정책 |
|------|--------|-----------|
| `210.96.71.194` (IP) | 메인 GSCert 앱 | 그대로 IP로 서비스(사내 직결). `/consultation/` 로 오면 `gsai.tta.or.kr` 로 302 |
| `gsai.tta.or.kr` (도메인) | 메인 GSCert 앱 + 상담 앱(8787) | `/` 는 메인 앱, `/consultation/` 은 8787 프록시 |

- IP→도메인 리다이렉트는 **302(임시)**. 상담(구글 OAuth)에만 적용되며, 메인 앱은 IP/도메인 모두
  그대로 통과한다(위 표 참고).
- **IP 단독 접속과 `nip.io` 임시 도메인은 폐기**했다. 브라우저·구글 콘솔·8787 설정 어디에도
  더 이상 `nip.io` 값이 남지 않아야 한다.

---

## 2. 194 측에서 만진 파일

| 파일 | 내용 |
|------|------|
| `setup/nginx.conf` (템플릿) | 443 서버에 `location /consultation/`(프록시+IP→도메인 302), `server_name __SERVER_IP__ __SERVER_DOMAIN__` |
| `env.ps1` (실서버, git 미포함) | `$env:SERVER_DOMAIN = "gsai.tta.or.kr"` 추가 — Django·nginx 양쪽이 이 값을 읽음 |
| `setup/Update-NginxConf.ps1` | `$env:SERVER_DOMAIN` 있으면 그 값, 없으면 `<ip>.nip.io` 폴백. `__SERVER_DOMAIN__` 치환 |
| `setup/gen_self_signed_cert.ps1` | `-ServerDomain` 파라미터로 인증서 SAN 에 `IP:<ip>,DNS:<domain>` 동시 등록, CN=도메인 |
| `myproject/settings.py` | `SERVER_DOMAIN` 이 설정되면 `DOWNLOAD_REVIEW_*_BY_HOST`/`CSRF_TRUSTED_ORIGINS` 에 도메인 별칭 자동 등록 |
| `C:\nginx-1.29.8\conf\nginx.conf` (실서버, git 미포함) | 위 템플릿을 리터럴 값(`gsai.tta.or.kr`)으로 반영 |

> 실서버 `nginx.conf` 는 템플릿에서 생성되는 산출물이다. 값이 꼬이면
> `env.ps1` 로드 후 `setup/Update-NginxConf.ps1 -Mode All` 재실행(또는 `start_nginx.ps1`)해서
> 다시 만들면 된다.

> **검토했지만 채택하지 않은 방법**: Cloudflare Tunnel(`setup/cloudflared-config.yml`,
> `setup/install_cloudflared.ps1`). 전산팀이 `gsai.tta.or.kr` 을 194 IP로 직접 A레코드 등록해줬기
> 때문에 터널 없이 기존 nginx+자체서명 인증서 구조 그대로 도메인을 서비스할 수 있다. 위 두 파일은
> 미사용 참고용으로 남겨둔 것이며, 실제로 Cloudflare Tunnel 을 쓰게 될 경우에만 참고한다.

---

## 3. 인증서 (자체서명 + 사내 루트 신뢰)

도메인으로 접속하려면 인증서 SAN 에 그 도메인이 있어야 브라우저 이름-불일치 경고가 안 뜬다.
갱신 명령(도메인 바뀌면 `-ServerDomain` 만 교체):

```powershell
powershell -ExecutionPolicy Bypass -File C:\Claude_GSCert\setup\gen_self_signed_cert.ps1 `
  -ServerIp 210.96.71.194 -ServerDomain gsai.tta.or.kr
# 생성 후: nginx.exe -t  &&  nginx.exe -s reload (또는 start_nginx.ps1)
```

- (2026-08) 위 명령으로 이미 재생성 완료 — SAN: `IP:210.96.71.194, DNS:gsai.tta.or.kr`.
- 인증서를 재생성하면 지문이 바뀌므로, 기존에 `gscert.crt` 를 "신뢰할 수 있는 루트 인증 기관"에
  등록해둔 **사내 PC들에 새 gscert.crt 를 재배포**해야 경고가 완전히 사라진다(1회 작업, GPO/certlm.msc).
- `gsai.tta.or.kr` 은 **회사 소유 공인 도메인**이므로, 공개 DNS 통제 권한이 있다면 Let's Encrypt
  (DNS-01) 로 **무경고 공인 인증서** 발급도 가능하다(자체서명 재배포가 필요 없어짐). 필요하면
  추가로 진행할 수 있다 — 별도 작업으로 분리.

---

## 4. gsai.tta.or.kr 전환 상태 (2026-08)

| # | 위치 | 상태 | 담당 |
|---|------|------|------|
| 1 | TTA DNS A레코드 (`gsai.tta.or.kr → 210.96.71.194`) | ✅ 완료 | TTA 전산팀 |
| 2 | `env.ps1` 의 `$env:SERVER_DOMAIN = "gsai.tta.or.kr"` | ✅ 완료 | 우리 |
| 3 | 실서버 `nginx.conf` 재생성(`Update-NginxConf.ps1 -Mode All`) | ✅ 완료(파일만, 아래 5 대기) | 우리 |
| 4 | 자체서명 인증서 SAN 을 `gsai.tta.or.kr` 로 재발급 | ✅ 완료 | 우리 |
| 5 | **nginx reload** (`start_nginx.ps1` 또는 `nginx -s reload`) | ⏳ 대기 — 8787 팀 준비 시점과 맞춰서 진행 | 우리 |
| 6 | **Django 앱 재기동** (main 앱이 `SERVER_DOMAIN` 을 읽도록) | ⏳ 대기 — 5와 같은 시점에 진행 | 우리 |
| 7 | 구글 콘솔 승인된 리디렉션 URI 에 `https://gsai.tta.or.kr/consultation/auth/callback` 추가 | ⏳ 8787 팀 확인 필요 | 8787 |
| 8 | 8787 앱의 `auth.redirect_uri` 를 새 도메인으로 변경 | ⏳ 8787 팀 확인 필요 | 8787 |

8787 팀에 전달한 내용은 [CONSULTATION_DOMAIN_CUTOVER_FOR_8787_TEAM.md](CONSULTATION_DOMAIN_CUTOVER_FOR_8787_TEAM.md) 참고.

> 5·6번(실제 반영)은 8787 팀의 7·8번이 끝나기 전에 실행하면, IP로 들어온 상담 접속이
> `gsai.tta.or.kr` 로 리다이렉트된 후 구글 로그인이 `redirect_uri_mismatch` 로 실패한다.
> 8787 팀 확인 후 같은 시점에 5·6번을 실행한다.

> 접두어 `CONSULT_BASE_PREFIX=/consultation` 는 도메인 교체와 무관하게 **그대로** 둔다.

---

## 5. 검증 명령 (전환 후)

```powershell
# IP 상담 접속 → 도메인으로 302 되는지
curl.exe -k -s -o NUL -w "%{http_code} -> %{redirect_url}`n" https://210.96.71.194/consultation/
# 도메인 상담 → 8787 프록시(200/401)
curl.exe -k -s -o NUL -w "%{http_code}`n" https://gsai.tta.or.kr/consultation/
# 도메인으로 메인앱 접속 → 200(IP로 되돌리지 않음)
curl.exe -k -s -o NUL -w "%{http_code}`n" https://gsai.tta.or.kr/
```
