# ECM 연동 코딩 참고 (Playwright / WebSocket / 다운로드 팝업)

ECM(DestinyECM) 자동화 관련 코드를 작성·수정할 때 반복적으로 필요한 지식을 모아둔 참고
문서. 새 ECM 기능을 만들 때 여기부터 읽는다.

## 1. 서버 실행 환경 (중요 제약)

- 웹 서버는 `manage.py runserver --noreload` 로 뜨지만, **Channels 4.x + daphne** 로
  ASGI(WebSocket)를 서빙한다. `INSTALLED_APPS` **최상단에 `'daphne'`** 가 있어야
  runserver 가 ASGI 로 뜬다(없으면 WSGI → `/ws/` 가 404 → 프론트 "웹소켓 오류").
- **daphne 는 Windows 에서 `WindowsSelectorEventLoopPolicy` 를 강제**한다(Twisted 호환).
  그런데 **Playwright 는 브라우저 하위 프로세스 실행에 `ProactorEventLoop` 가 필요**하다.
  → **ASGI(Selector) 루프에서 Playwright 를 직접 띄우면 `NotImplementedError`.**
  - 해결: Playwright 작업은 **전용 ProactorEventLoop 스레드**에서 실행하고, ASGI 컨슈머는
    `asyncio.run_coroutine_threadsafe(coro, worker_loop)` + `await asyncio.wrap_future(cf)`
    로 그 스레드에 잡을 넘기고 결과를 받는다. (`playwright_job/consumers.py` 참고)
  - 별도 프로세스(예: `run_download_worker` 관리명령)는 `asyncio.run`(기본 Proactor)이라
    이 문제가 없다.
- 환경변수(GEMINI/PG 비밀번호 등)는 **프로세스 시작 시점에만 상속**된다. 값 변경 후에는
  서버/워커를 **재시작**해야 반영된다. 비밀값은 `env.ps1`(비밀 없음) + `set-secrets.ps1`
  (시스템 환경변수 저장) 구조를 쓴다.

## 2. Chrome 실행 인자 (사설망 ECM 필수)

ECM 은 사설망(예: `210.104.181.10`)이라 Chrome 의 **Local Network Access** 검사에 막혀
좌측 폴더 트리/리소스가 로드되지 않는다("좌측 트리 로딩 실패"). **`chrome://flags` 수동
변경은 Playwright 가 띄우는 별도 Chromium 에 적용되지 않는다** — 반드시 실행 인자로 준다:

```
--disable-features=LocalNetworkAccessCheck,LocalNetworkAccessChecks
--disable-local-network-access-check
```

적용 위치: `main/views/review/ecm_download.py:launch_browser`(다운로드 워커),
`main/utils/weekly.py:ensure_page`(weekly), `playwright_job/apps.py:_launch_browser`(URL/문서
워커). **새 브라우저 실행 코드를 추가하면 이 인자를 반드시 포함할 것.**

## 3. 한글 경로 정규화 (NFC)

ECM 웹(DOM)에서 가져온 폴더명은 한글이 **NFD(분해형)** 일 수 있는데, Windows 는 폴더를
**NFC(조합형)** 로 만든다. 다운로드 대기/파일 목록 시 경로를 NFC 로 통일하지 않으면
`os.listdir` 가 폴더를 못 찾아(0개) 대기가 타임아웃된다.

```python
import unicodedata
seg = unicodedata.normalize("NFC", seg)
```

- 파일 존재/목록 확인은 **재귀(os.walk)** 로 한다(ECM 이 하위 폴더에 내려받는 경우 있음).
- 참고: `main/views/review/ecm_agent_popup.py` 의 `_list_download_files`,
  `_navigate_to_download_target`(경로 세그먼트 NFC).

## 4. 다운로드 폴더 팝업 처리 (핵심 재사용 코드)

ECM 에서 "파일 다운로드"를 누르면 `DestinyECMAgent` 가 **Windows "폴더 찾아보기"** 대화상자를
띄운다. 이 팝업을 다루는 검증된 코드가 `main/views/review/ecm_agent_popup.py` 에 있다.

- 진입점: `handle_folder_popup_and_download(project_number, job_id, max_retries, relative_path,
  center_code, base_dir=None)`
  - `base_dir` 미지정 시 `AGENT_DOWNLOAD_BASE_DIR`(=`C:\Users\Administrator\download`).
    다른 위치(예: report)로 받으려면 `base_dir` 를 넘긴다.
- 폴더 선택 방식(안정성 순서):
  1. **대상 폴더를 디스크에 미리 생성**(`os.makedirs`, NFC) 후 **`BFFM_SETSELECTION`**
     메시지로 그 경로를 곧장 선택 → "새 폴더 만들기"/인라인 편집/UIA 트리 검색 회피.
  2. 실패 시 폴백: 키보드 이동(`Shift+Tab`/방향키) + 인라인 폴더 생성.
- 확인/버튼은 **전역 키 입력(SendInput) 대신 창 메시지(BM_CLICK / WM_CHAR / SendMessage)** 로
  누른다. SendInput 은 세션 잠금/원격 끊김/포커스 없음 시 0 이벤트로 실패한다.
- 다운로드 완료 판정: 대상 폴더를 **재귀**로 폴링해 파일 개수·크기가 안정화될 때까지 대기.

### SendInput 이 실패하는 이유 (자주 겪음)
- RDP 세션 잠김/연결 끊김 → 입력 데스크톱 비활성 → `SendInput() inserted only 0 ...`.
- 메시지 기반(SetFocus+SendMessage, BM_CLICK)은 포커스/잠금과 무관하게 동작 → 이걸 우선.

## 5. ECM 트리 탐색 단계 (인증일자 경로: 시험이력용)

`playwright_job/tasks.py:run_playwright_task_on_page` 의 단계(재사용 가능):

| 단계 | 함수(`playwright_job/common.py`) | 동작 |
|---|---|---|
| S1 | `goto_base` | ECM 기본 URL 이동 |
| S2 | `wait_left_tree` | 좌측 폴더 트리 로딩 |
| S3 | `click_year` | 연도 폴더(인증일자 연도) |
| S4 | `click_committee` | 인증심의위원회 폴더 |
| S5 | `click_date_folder` | 인증일자 폴더 |
| S6 | `click_test_folder` | 시험번호 폴더 |
| S7~ | (기능별로 다름) | 문서 클릭/URL 복사 또는 전체선택/다운로드 |

프로젝트 폴더 경로(다운로드-리뷰용, 03 GS시험인증→프로젝트)는
`main/views/review/ecm_download.py` 의 `navigate_to_project_folder` /
`run_ecm_recursive_downloads` 를 쓴다. **문서 목록 전체선택 + 다운로드 트리거**는
`select_all_documents(page)` + `click_download_menu(page)` 재사용.

## 6. WebSocket 잡 프로토콜 (URL/문서 워커)

- 라우트: `/ws/run_job/` (`playwright_job/routing.py` → `PlaywrightJobConsumer`).
- 요청: `{"인증일자": "...", "시험번호": "...", "action": "url" | "document"}`
  - `action` 없으면 기존 동작(`url`)로 간주.
- 응답 status: `hello` → `wait`/`processing` → `success`(+`url` 또는 `download_url`) | `error`.
- 컨슈머는 먼저 **캐시**를 보고, miss 일 때만 ECM 자동화를 워커(Proactor 스레드)에 넘긴다.
  - URL: `main/data/ecmURL.db` 의 `ecm_url(test_no, url)`.
  - 문서: `C:\Users\Administrator\report\<시험번호>` 폴더 존재(+파일 ≥1) 여부.

## 7. nginx (프록시)

- 활성 설정: `C:\nginx-1.29.8\conf\nginx.conf` (리포 템플릿: `setup/nginx.conf`).
- `/ws/` 에 WebSocket 업그레이드 헤더 필요:
  `proxy_http_version 1.1; Upgrade $http_upgrade; Connection "upgrade";`
- 큰 업로드(유사검색 문서 등) 대비 `client_max_body_size 200m`.
- reload 가 Windows 에서 자주 실패(`OpenEvent ... failed`) → **전체 재시작**(stop→start)이 확실.
- **주의**: PowerShell `Set-Content -Encoding UTF8` 은 BOM 을 붙여 nginx 가 1행을 못 읽는다.
  `[IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))` 로 무-BOM 저장.

## 8. 자주 나온 오류 → 원인 요약

| 증상 | 원인 |
|---|---|
| 프론트 "웹소켓 오류" | `daphne` 미등록으로 runserver 가 WSGI → `/ws/` 404 |
| `NotImplementedError`(get_browser_safe 실패) | ASGI(Selector) 루프에서 Playwright 실행 → Proactor 스레드 필요 |
| "좌측 트리 로딩 실패"(S2) | 브라우저에 Local Network Access 비활성화 인자 누락 |
| 다운로드 대기 300s 타임아웃(파일은 존재) | 경로 NFC/NFD 불일치, 또는 하위폴더에 저장(비재귀 목록) |
| `SendInput() inserted only 0 ...` | 세션 잠금/포커스 없음 → 메시지 기반 입력으로 대체 |
| 폴더/확인 안 눌림(BFFM 이후) | 대화상자가 포그라운드 아님 → 전역 키 대신 버튼 메시지 클릭 |
| "Unexpected token '<'"(유사검색 등) | 업로드가 nginx `client_max_body_size` 초과 → 413 HTML |
