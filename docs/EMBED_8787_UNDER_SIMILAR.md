> ⚠️ **참고(2026-08)**: 이 문서는 초기 검토 초안이다. 실제 구현은 `/similar/` 가 아니라
> `/consultation/` 경로의 리버스 프록시(방식 A)로 진행됐고, 접속 도메인도 `nip.io` 를 거쳐
> 정식 도메인 `gsai.tta.or.kr` 로 전환됐다. 최신 상태는
> [CONSULTATION_PROXY_SETUP.md](CONSULTATION_PROXY_SETUP.md) 와
> [CONSULTATION_DOMAIN_CUTOVER_FOR_8787_TEAM.md](CONSULTATION_DOMAIN_CUTOVER_FOR_8787_TEAM.md) 를 참고.

# 8787 앱을 `https://210.96.71.194/similar/` 아래에 임베드하기 — 8787 개발팀 전달 문서

> 목적: 8787 포트 앱(`https://210.96.71.67.nip.io:8787/`, Google 계정 로그인 사용)의
> 화면을 우리 서비스의 `https://210.96.71.194/similar/` 헤더 아래 영역에 표시한다.
> **브라우저 주소창에는 우리 주소(`210.96.71.194`)만 보이고, 내용은 8787 앱이 렌더링**되도록 한다.
>
> 이 문서는 8787 앱을 개발·운영하는 팀이 **자기 쪽에서 바꿔야 할 것**을 정리한 것이다.
> 우리(194 측)가 할 일은 문서 끝의 "우리 측 작업" 절에 참고용으로 적어둔다.

---

## 0. 왜 그냥 iframe만으로는 안 되는가 (배경)

단순히 `<iframe src="https://...8787/">` 한 줄로는 **로그인 단계에서 반드시 깨진다.** 이유:

1. **Google 로그인 페이지(`accounts.google.com`)는 iframe 프레이밍을 원천 차단**한다
   (`X-Frame-Options: DENY`). 리다이렉트 방식 OAuth를 쓰면 로그인 순간 하얀 화면이 된다.
2. 크로스 오리진 iframe 안의 세션 쿠키는 **서드파티 쿠키**로 취급되어 최신 브라우저에서 차단되는 추세다.

그래서 아래 **두 가지 방식 중 하나**를 선택해야 하며, 각각 8787 앱에서 바꿔야 할 것이 다르다.

| 방식 | 주소 위장 | 로그인 안정성 | 8787 앱 수정량 | 권장 |
|------|:---:|:---:|:---:|:---:|
| **A. 리버스 프록시** (194가 8787을 대신 호출) | 완전 | 높음(전부 우리 도메인=1st party) | 중 | ✅ 1순위 |
| **B. iframe + 팝업 로그인** | 됨(임베드) | 중(서드파티 쿠키 이슈) | 소~중 | 대안 |

---

## 방식 A — 리버스 프록시 (권장)

194 서버의 Nginx가 `/similar/` 경로 요청을 받아 뒤에서 8787 앱을 호출한다.
브라우저 입장에서는 **처음부터 끝까지 `https://210.96.71.194` 하나의 오리진**만 존재한다.
따라서 쿠키·CORS·프레이밍 문제가 대부분 사라진다. 대신 8787 앱이 **서브경로(`/similar/`) 뒤에
있어도 정상 동작**하고, **프록시 헤더를 신뢰**하도록 만들어져야 한다.

### A-1. Google Cloud Console (OAuth 클라이언트) 설정 — ⭐ 필수

해당 OAuth 2.0 클라이언트 ID 설정에 아래를 **추가**한다 (기존 값은 지우지 말 것):

- **승인된 JavaScript 원본 (Authorized JavaScript origins)**
  ```
  https://210.96.71.194
  ```
- **승인된 리디렉션 URI (Authorized redirect URIs)**
  ```
  https://210.96.71.194/similar/<앱의_OAuth_콜백경로>
  ```
  예) 앱 콜백이 `/auth/google/callback` 이면 → `https://210.96.71.194/similar/auth/google/callback`

> 반영에 몇 분~수십 분 걸릴 수 있음. `redirect_uri_mismatch` 오류가 나면 이 값이 원인이다.

### A-2. 앱이 "프록시 뒤"에 있음을 인지하도록 (X-Forwarded-* 신뢰) — ⭐ 필수

프록시를 거치면 앱이 보는 요청 정보가 실제 브라우저가 본 주소와 달라진다.
앱은 아래 헤더를 신뢰해 **자신의 외부 주소를 `https://210.96.71.194/similar` 로 인식**해야 한다.

194 프록시가 보내줄 헤더:
```
X-Forwarded-Proto: https
X-Forwarded-Host:  210.96.71.194
X-Forwarded-Prefix: /similar
```

프레임워크별 처리 예:

- **Flask / Werkzeug**
  ```python
  from werkzeug.middleware.proxy_fix import ProxyFix
  app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)
  ```
- **Django** (`settings.py`)
  ```python
  SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
  USE_X_FORWARDED_HOST = True
  FORCE_SCRIPT_NAME = "/similar"        # 서브경로 인식
  # 로그인/정적 파일 경로도 /similar 접두어를 타도록
  STATIC_URL = "/similar/static/"
  ```
- **Node/Express**
  ```js
  app.set("trust proxy", true);
  ```
- **Spring Boot** (`application.properties`)
  ```properties
  server.forward-headers-strategy=framework
  server.servlet.context-path=/similar
  ```

핵심: **OAuth 시작 시 앱이 Google에 넘기는 `redirect_uri` 가
`https://210.96.71.194/similar/...` 로 만들어져야 한다.** (위 헤더를 신뢰하면 대부분 자동 처리됨)

### A-3. 서브경로(`/similar/`)에서도 리소스가 깨지지 않도록 — ⭐ 중요

앱이 HTML에서 **루트 절대경로(`/static/...`, `/api/...`)**를 하드코딩하면, 브라우저는 이를
`https://210.96.71.194/static/...`(=`/similar` 없음)로 요청해 404가 난다. 해결책 중 하나:

1. (권장) **상대경로** 또는 **설정 가능한 base 경로** 사용
   - HTML `<head>`에 `<base href="/similar/">` 추가, 또는
   - 프레임워크의 base-path 설정(위 `FORCE_SCRIPT_NAME` / `context-path` / Vite·CRA의 `base`) 사용
2. 프론트 빌드 도구를 쓰면:
   - **Vite**: `base: '/similar/'`
   - **CRA**: `"homepage": "/similar"` (package.json)
   - **Next.js**: `basePath: '/similar'` (next.config.js)

> 절대경로를 완전히 없애기 어려우면 194 쪽에서 `sub_filter`로 치환할 수도 있으나,
> 앱 업데이트마다 깨질 수 있어 **앱 자체를 base-path 인식하게 만드는 편**을 강력 권장한다.

### A-4. 쿠키 — 대개 그대로 OK

리버스 프록시에서는 사용자 브라우저가 오직 `210.96.71.194`만 보므로 세션 쿠키는 **1st-party**다.
- 쿠키 도메인을 `210.96.71.67.nip.io` 로 **하드코딩하지 말 것** (도메인 미지정=현재 호스트 기본값 권장).
  하드코딩되어 있으면 194 프록시에서 재작성해야 하니 알려달라.
- `SameSite=Lax`, `Secure` 로 충분하다.

### A-5. 프레이밍 헤더 — 방식 A에서는 불필요

방식 A는 iframe을 쓰지 않고 194 페이지 안에 직접 프록시 렌더링하므로
`X-Frame-Options` / `frame-ancestors` 조정이 필요 없다. (방식 B에서만 필요)

---

## 방식 B — iframe + 팝업 로그인 (대안)

194 페이지에 `<iframe src="https://210.96.71.67.nip.io:8787/...">` 를 넣는다.
주소창은 194로 보이고, iframe 내부만 8787이 렌더링한다. 8787 앱을 서브경로로 옮길 필요가 없어
**앱 수정량이 적다.** 대신 크로스 오리진 iframe이라 아래가 필요하다.

### B-1. 프레이밍 허용 헤더 — ⭐ 필수

8787 앱의 **모든 응답 헤더**에서:
- `X-Frame-Options` 헤더는 **제거** (있으면 안 됨)
- 대신 CSP로 우리 오리진만 허용:
  ```
  Content-Security-Policy: frame-ancestors https://210.96.71.194
  ```

### B-2. 로그인은 반드시 "팝업 방식"으로 — ⭐ 필수

Google 로그인 페이지는 iframe 안에서 안 열리므로, 로그인을 **새 팝업 창**으로 띄워야 한다.
- Google Identity Services / Firebase Auth의 **`signInWithPopup`** 계열 사용
  (리다이렉트 방식 `signInWithRedirect`는 iframe 안에서 깨진다)
- OAuth Console 설정은 **기존 8787 도메인 값 그대로**면 된다
  (팝업은 8787 오리진에서 뜨므로). 즉 A-1 같은 194 등록이 **불필요**.

### B-3. 쿠키 — 서드파티 대응 — ⭐ 필수

iframe 내부 8787 세션 쿠키는 브라우저 입장에서 **서드파티 쿠키**다. 반드시:
```
Set-Cookie: session=...; SameSite=None; Secure
```
- `SameSite=None` 없으면 iframe 안에서 로그인 세션이 유지되지 않는다.
- 그래도 **Safari(ITP) 및 서드파티 쿠키 차단 설정** 사용자는 로그인 안 될 수 있다.
  이 한계 때문에 로그인 앱은 **방식 A(리버스 프록시)를 1순위로 권장**한다.

---

## 권장 결론

- **로그인 세션 안정성이 중요하므로 → 방식 A(리버스 프록시)를 채택**하는 것을 추천.
- 8787 앱에서 꼭 해줄 것 (방식 A 기준):
  1. **[Google Console]** JS 원본 + 리디렉션 URI에 `https://210.96.71.194[/similar/...]` 추가
  2. **[앱]** `X-Forwarded-Proto/Host/Prefix` 헤더 신뢰 설정
  3. **[앱]** 서브경로 `/similar/` 에서 정적/API 경로가 안 깨지도록 base-path 인식
  4. **[앱]** 쿠키 도메인 하드코딩 여부 확인(가급적 미지정)
- 앱을 서브경로로 옮기기 어렵다면 **방식 B**로 진행 (B-1·B-2·B-3만 처리).

---

## 우리(194) 측 작업 — 참고용 (8787 팀이 할 일 아님)

방식 A의 Nginx 리버스 프록시 예시(우리 서버에 우리가 설정):
```nginx
location /similar/ {
    proxy_pass https://210.96.71.67.nip.io:8787/;
    proxy_http_version 1.1;

    # 프록시 뒤임을 앱에 알림
    proxy_set_header Host              210.96.71.67.nip.io:8787;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host  210.96.71.194;
    proxy_set_header X-Forwarded-Prefix /similar;
    proxy_set_header X-Real-IP         $remote_addr;

    # 업스트림 TLS(SNI) 및 인증서 검증
    proxy_ssl_server_name on;

    # 쿠키 도메인/경로를 우리 쪽으로 재작성
    proxy_cookie_domain 210.96.71.67.nip.io 210.96.71.194;
    proxy_cookie_path   /  /similar/;

    # WebSocket 쓰면
    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

방식 B라면 우리는 헤더 페이지에 아래만 넣으면 된다:
```html
<iframe src="https://210.96.71.67.nip.io:8787/"
        style="width:100%;height:80vh;border:0"
        referrerpolicy="no-referrer-when-downgrade"></iframe>
```

---

## 8787 팀에 되묻고 싶은 것 (확인 요청)

1. 앱 프레임워크/언어는 무엇인가? (Flask/Django/Node/Spring 등 → 위 설정 예시 특정 가능)
2. OAuth 콜백 경로(redirect path)는 정확히 무엇인가? (예: `/auth/google/callback`)
3. 로그인은 리다이렉트 방식인가, 팝업 방식인가?
4. 세션 쿠키에 도메인을 하드코딩하는가?
5. 정적 리소스/API를 루트 절대경로(`/static`, `/api`)로 부르는가, base-path 설정이 가능한가?

위 5개만 알려주면 방식 A/B 중 최종안과 정확한 설정값을 확정해 회신하겠다.
