# myproject 앱 코드 구성 요약 (WSGI/ASGI + WebSocket 라우팅)

이 문서는 **myproject 앱**에 있는 아래 파일들을 대상으로,
`main`, `playwright_job`(Channels/WebSocket)과 어떻게 엮여 동작하는지 정리합니다.

대상 파일(5개)
- `myproject/asgi.py`
- `myproject/routing.py`
- `myproject/settings.py`
- `myproject/urls.py`
- `myproject/wsgi.py`

---

## 0) 한 줄 결론

- **HTTP 요청**은 `WSGI` 또는 `ASGI`에서 `Django`가 처리합니다.
- **WebSocket 요청**은 `ASGI`에서만 처리되며, `myproject/routing.py`가 `main` + `playwright_job`의 websocket URL 패턴을 합쳐 제공합니다.

---

## 1) `asgi.py` — HTTP + WebSocket을 동시에 받는 “ASGI 진입점”

### 역할
- Windows 환경에서 Playwright 서브프로세스 동작 안정화를 위해, import 초기에 **Proactor 이벤트 루프 정책**을 설정합니다.
- `ProtocolTypeRouter`를 사용해 프로토콜별 라우팅을 분기합니다.
  - `"http"`: `get_asgi_application()` (일반 Django HTTP)
  - `"websocket"`: `AuthMiddlewareStack(URLRouter(project_routing.websocket_urlpatterns))`
    - 인증 미들웨어(세션/쿠키)를 WebSocket에도 적용
    - 실제 WebSocket URL 패턴은 `myproject.routing.websocket_urlpatterns`를 사용

### 왜 이렇게 되어 있나?
- 기존 “WSGI + gunicorn”만으로는 WebSocket 처리가 불가합니다.
- Channels를 쓰는 경우, **ASGI 서버(Uvicorn/Daphne)**가 WebSocket을 받고,
  같은 `application` 안에서 HTTP도 함께 처리하도록 구성하는 것이 표준 패턴입니다.

---

## 2) `routing.py` — WebSocket URL을 main + playwright_job에서 “합쳐서 제공”

### 역할
- `main.routing`과 `playwright_job.routing`을 import
- 각 앱의 `websocket_urlpatterns`를 **리스트 덧셈으로 합쳐** 하나로 만듭니다.

즉, WebSocket URL은 “프로젝트(myproject)”가 최종적으로 통합하고,
앱별로 routing을 분리해 유지보수하기 쉽게 만든 구조입니다.

---

## 3) `settings.py` — Channels/ASGI 활성화 + 앱 등록 + 정적파일 경로

### 핵심 설정 포인트

#### 3.1 Channels 활성화
- `INSTALLED_APPS`에 `channels`가 들어가 있고,
- `ASGI_APPLICATION = 'myproject.asgi.application'`으로 지정되어 있습니다.
- 동시에 `WSGI_APPLICATION = 'myproject.wsgi.application'`도 유지됩니다.
  - 즉 배포 방식에 따라 WSGI/ASGI 둘 다 쓸 수 있는 “겸용” 설정입니다.

#### 3.2 앱 로딩 순서/ready() 호출
- `main.apps.MainConfig`를 문자열로 명시해서 `ready()`가 호출되도록 해둔 주석이 있습니다.
- `playwright_job`도 INSTALLED_APPS에 포함되어 있어,
  Channels consumer + worker + Playwright 풀 구조가 서버에서 동작할 수 있습니다.

#### 3.3 정적파일(Static) 설정
- `STATIC_ROOT = BASE_DIR/staticfiles`
- `STATICFILES_DIRS`에 `main/static`이 들어가 있어,
  main 앱의 JS/CSS가 collectstatic 전에 개발 환경에서도 바로 로드되도록 구성되어 있습니다.

---

## 4) `urls.py` — HTTP URL 라우팅(메인/관리자/로그인)

### 역할
- `path('', include('main.urls'))`로 **HTTP 라우팅 대부분을 main 앱이 담당**
- `accounts/`는 Django 기본 auth URL(로그인/로그아웃 등)
- `admin/`은 관리자 페이지

중요: WebSocket URL은 여기(`urls.py`)에 등록하지 않습니다.  
WebSocket은 `asgi.py` → `myproject.routing.py` → (각 앱 routing)으로만 흐릅니다.

---

## 5) `wsgi.py` — 전통적인 HTTP 전용 진입점(WSGI)

### 역할
- 표준 Django WSGI 엔트리입니다.
- `get_wsgi_application()`만 노출합니다.

언제 쓰나?
- WebSocket이 필요 없는 환경(또는 별도의 WS 서버를 운용)에서
  gunicorn/uwsgi 같은 WSGI 서버로 HTTP만 처리할 때 사용합니다.

---

## 6) 실제 요청 흐름(콜 플로우)

### 6.1 HTTP 요청
```
Client (HTTP)
  → (WSGI: myproject/wsgi.py) 또는 (ASGI: myproject/asgi.py 의 "http")
  → Django URLConf: myproject/urls.py
  → main.urls → main.views ...
```

### 6.2 WebSocket 요청(예: History에서 ECM 자동화 실행)
```
Client (WebSocket)
  → myproject/asgi.py 의 "websocket"
  → AuthMiddlewareStack
  → URLRouter(myproject.routing.websocket_urlpatterns)
  → playwright_job.routing.websocket_urlpatterns
  → PlaywrightJobConsumer (consumers.py)
  → 작업 큐/워커(tasks.py/ecm.py...) 실행
  → success(url) 메시지 반환
```

---

## 7) 실무 관점 체크 포인트(짧게)

- **운영에서 WebSocket이 필요하면 WSGI만으로는 안 됨**
  - 반드시 ASGI 서버(Uvicorn/Daphne)가 떠 있어야 합니다.
- **Windows + Playwright**
  - `asgi.py` 초기에 Proactor 정책을 잡아두지 않으면,
    Playwright 서브프로세스/파이프 처리에서 애매한 문제가 터질 수 있어 지금 구조가 합리적입니다.
- **WebSocket URL 통합 위치**
  - “프로젝트 routing에서 앱 routing을 합친다”는 구조 덕분에,
    앱 단위로 routing을 유지하면서도 한 번에 연결할 수 있습니다.
