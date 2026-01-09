# playwright_job (History-ECM URL 자동 오픈) 서버 코드 구성 요약

이 문서는 **History 화면에서 ECM URL을 자동으로 생성/열기 위해 서버에서 동작하는 Playwright 코드들**(총 9개)을 대상으로,
각 파일의 역할과 **서로 어떤 파일/함수가 어떤 파일을 호출하는지**를 정리합니다.

대상 파일(9개)
- `apps.py` *(대화로 제공된 코드)*  
- `routing.py`
- `consumers.py`
- `tasks.py`
- `ecm.py`
- `selectors.py`
- `common.py`
- `clipboard.py`
- `parsers.py`

---

## 0) 전체 흐름(한 장 요약)

1) **프론트(History)**에서 `history_ECM.js`가 WebSocket으로 `ws/run_job/`에 `{인증일자, 시험번호}` 전송  
2) Django Channels의 **`PlaywrightJobConsumer`**가 요청을 받아 **작업 큐에 등록**하고 `wait → processing` 상태 메시지 전송  
3) 서버의 **단일 워커(_worker_loop)**가 큐에서 작업을 꺼내:
   - 브라우저 풀에서 브라우저를 확보(`get_browser_safe`)
   - 동일한 context/page를 재사용하며 Playwright 자동화를 실행(`run_playwright_task_on_page`)
4) 자동화가 ECM 화면에서 URL 복사를 수행하고, **클립보드에서 URL을 파싱**해 `{url}` 반환  
5) Consumer가 `success`로 `{url}`을 다시 WebSocket으로 전달  
6) 프론트가 받은 URL을 새 탭으로 `window.open(url)`하여 ECM 문서를 연다

---

## 1) 파일별 역할 요약

## 1.1 `apps.py` — Playwright 런타임 1회 시작 + 브라우저 풀(Queue) 관리(AppConfig)
**핵심 역할**
- 전역 Playwright 런타임(`_playwright`)을 **딱 1번만** 시작하도록 `_ensure_playwright_started()`에서 락으로 보호
- 브라우저를 POOL_SIZE(기본 5)까지 재사용하는 **브라우저 풀(`BROWSER_POOL`)** 운영
- `get_browser_safe()`:
  - 풀에서 꺼내 “살아있으면” 반환
  - 없거나 죽었으면 즉시 새로 launch해서 반환(게으른 확보)
- `put_browser_safe()`:
  - 살아있고 큐 여유가 있으면 반환, 아니면 close
- `PlaywrightJobConfig.ready()`:
  - 서버 시작 시(이벤트루프가 이미 돌고 있으면) **선택적으로** `_warmup_pool()`을 background task로 돌려 미리 브라우저를 채움
- Windows에서 이벤트루프 정책을 Proactor로 맞추려는 방어 로직 포함

**이 파일이 해결하는 문제**
- 요청마다 Playwright 런타임을 새로 띄우면 너무 느리고 불안정 → **런타임 1회 + 브라우저 재사용**으로 안정화

---

## 1.2 `routing.py` — WebSocket 라우팅 등록
- `ws/run_job/` 경로를 `PlaywrightJobConsumer`에 연결합니다.
- Channels 라우팅 모듈 로딩 여부를 로그로 확인 가능하도록 warning 출력이 포함되어 있습니다.

---

## 1.3 `consumers.py` — WebSocket Consumer + 전역 큐 + 단일 워커(직렬 처리)
**핵심 역할**
- **WebSocket 엔드포인트의 입구** (`PlaywrightJobConsumer`)
- 수신 JSON에서 `인증일자`, `시험번호`를 검증하고, 작업을 큐에 넣습니다.
- 클라이언트에 상태 메시지를 단계적으로 전송:
  - `wait`(대기열 정보 포함 가능) → `processing` → `success(url)` 또는 `error(...)`
- 전역 작업 큐/워커:
  - `_ensure_worker_started()`가 전역 큐(`_job_queue`)와 워커 task(`_worker_task`)를 1회만 생성
  - `_worker_loop()`가 큐를 소비하며 작업을 **항상 1개씩** 처리(직렬)
  - 실패 시 context/page를 reset하여 다음 작업이 “깨끗한 상태”에서 시작되도록 복구

**중요 포인트**
- **단일 워커 + 단일 page 재사용** 구조라 “동시에 여러 사용자가 요청해도” 실제 브라우저 조작은 직렬로 실행됨
- 대신 대기열 정보를 제공하여 UX를 보완

**호출 관계**
- `PlaywrightJobConsumer.receive()` → `enqueue_playwright_job()`  
- (worker) `run_playwright_task_on_page()` 호출 전에 `get_browser_safe()`로 브라우저 확보

---

## 1.4 `tasks.py` — Playwright 자동화를 “Step(1~9)”로 나눠 실행 + 실패 스크린샷/로그
**핵심 역할**
- ECM 자동화 흐름을 **Step 번호(1~9)**로 쪼개서 실행하고, 각 단계에서 실패 시:
  - 스크린샷 저장
  - 요구사항에 맞춘 로그 형식(`시간 | 요청IP | S(step) | 오류종류 | 스크린샷`)
  - `StepError`로 캡슐화하여 Consumer가 사용자 메시지/디버그정보를 만들 수 있게 함
- `run_playwright_task_on_page(page, cert_date, test_no, request_ip)`:
  - 인증일자 파싱 → 연도/yyyymmdd 생성
  - 시험번호 정규식 패턴 생성
  - `ecm.py`의 단계별 함수들을 순서대로 호출

**호출 관계(핵심)**
- `tasks.py` → `common.py`(날짜/패턴/스크린샷 이름/timeout)
- `tasks.py` → `ecm.py`(실제 페이지 조작 step 함수들)

---

## 1.5 `ecm.py` — ECM UI 조작(폴더 이동 → 문서 클릭 → 파일 선택 → URL 복사 → 클립보드 파싱)
**핵심 역할**
- ECM 사이트 UI를 Playwright로 조작하는 “실제 자동화 로직”의 본체
- 단계별 함수 제공:
  - `goto_base()` : ECM_BASE_URL 이동 + 로딩 오버레이 제거 대기
  - `wait_left_tree()` : 좌측 트리 패널 로딩 확인
  - `click_year()` / `click_committee()` / `click_date_folder()` / `click_test_folder()` : 트리 이동
  - `click_document_in_list()` : 문서 목록에서 대상 문서(시험성적서 우선) 클릭
  - `wait_file_list()` : 파일 목록 로딩 확인
  - `select_target_file_and_copy_url()` : 파일 row 선택 후 “URL 복사” 버튼 → 클립보드에서 URL 획득
- 문서 클릭에서 로딩 지연 문제를 줄이기 위해:
  - `count()` 즉시판정 대신 `wait_for(state="visible")` 기반으로 대기하도록 구성
- 같은 내용이 복사되어도 실패하지 않도록:
  - 복사 직전에 `clipboard_set_text("")`로 클립보드를 비우고
  - “non-empty 될 때까지” 대기

**호출 관계**
- `ecm.py` → `selectors.py` (DOM selector 상수)
- `ecm.py` → `common.py` (BASE_URL, TIMEOUTS, 날짜/패턴, clipboard helper)

---

## 1.6 `selectors.py` — ECM 화면 CSS Selector 상수 모음
- 좌측 트리, 문서 목록 테이블, 파일 목록 row, “URL 복사 버튼” 등
  ECM UI 구조에 맞춘 selector를 한 군데로 모아둔 파일입니다.
- UI 변경 시 **가장 먼저 수정**해야 하는 포인트입니다.

---

## 1.7 `common.py` — 공통 유틸(시간/스크린샷명/날짜 파싱/시험번호 패턴/timeout/클립보드)
**핵심 역할**
- `ECM_BASE_URL`, `TIMEOUTS` 등 정책값
- 인증일자 파싱(`parse_cert_date`): `yyyy.mm.dd` 또는 `yyyy-mm-dd` 지원 → `(year, yyyymmdd)` 반환
- 시험번호 패턴(`build_testno_pattern`): `-`/`_` 혼용 매칭되도록 정규식 생성
- 클립보드 get/set + 대기:
  - pywin32 기반 sync 함수를 `asyncio.to_thread`로 감싸 비동기로 사용
  - `wait_clipboard_nonempty()`로 복사 완료를 안정적으로 감지

---

## 1.8 `clipboard.py` — (대안/레거시 성격) 클립보드 유틸 + sentinel + “변화 감지”
**무엇이 다른가**
- `common.py`의 `wait_clipboard_nonempty()`가 “비어있지 않음” 기준인 반면,
  `clipboard.py`는 sentinel을 만들어 **이전 값과 다름**을 감지하는 `wait_clipboard_not_equal()`을 제공합니다.
- `make_sentinel()` / `set_clipboard_text()` / `get_clipboard_text()` 등
  좀 더 범용적이고 재사용 가능한 형태로 구성되어 있습니다.

**현재 연결**
- 현재 자동화 본 흐름(`ecm.py`)은 `common.py`의 clipboard 함수를 사용하므로,
  `clipboard.py`는 **다른 구현/이전 버전 유틸**일 가능성이 큽니다.
  (향후 “같은 내용 복사” 문제를 sentinel 방식으로 풀고 싶다면 이 파일을 활용할 수 있습니다.)

---

## 1.9 `parsers.py` — 클립보드 텍스트에서 “파일 URL”만 고르는 파서
- `pick_best_file_url(clipboard_text)`:
  1) “시험성적서”가 포함된 줄의 URL 우선
  2) 아니면 `.doc/.docx/.hwp/.pdf` 확장자 힌트가 있는 줄의 URL
  3) 없으면 None
- 현재 `ecm.py`는 정규식으로 첫 URL을 바로 뽑고 있어,
  이 파서는 **더 정교한 선택 규칙이 필요할 때** 연결하기 좋은 “후처리 모듈”입니다.

---

## 2) 호출/의존 관계 그래프(요약)

```
(front) history_ECM.js
    └─ WebSocket "ws/run_job/"  ───────────────┐
                                               │
routing.py  ──>  consumers.py:PlaywrightJobConsumer.receive()
                       ├─ _ensure_worker_started()  (queue + worker 1회)
                       ├─ enqueue_playwright_job()  (future로 결과 대기)
                       └─ (worker) _worker_loop()
                             ├─ apps.py:get_browser_safe()
                             ├─ browser.new_context() / new_page()  (재사용)
                             └─ tasks.py:run_playwright_task_on_page()
                                   ├─ common.py:parse_cert_date(), build_testno_pattern(), TIMEOUTS...
                                   └─ ecm.py:goto_base() → ... → select_target_file_and_copy_url()
                                         ├─ selectors.py (DOM selector)
                                         └─ common.py:clipboard_set_text(), wait_clipboard_nonempty()
```

(옵션) 더 정교한 URL 선택 규칙이 필요하면:
- `ecm.py`의 URL 파싱 부분에서 `parsers.py:pick_best_file_url()`를 사용하도록 연결 가능

---

## 3) 운영/안정성 관점 포인트(짧게)

- **단일 워커 직렬 처리**
  - 동시에 요청이 많아지면 대기열이 길어질 수 있지만,
  - ECM 같은 “상태ful UI 자동화”는 직렬이 안정적입니다.

- **context/page 재사용**
  - 성공 시엔 재사용으로 성능 이점
  - 실패 시 reset 로직이 반드시 필요(현재 구현됨)

- **클립보드**
  - Windows 서버에서 pywin32가 필수
  - “복사 결과가 이전과 동일할 때” 문제는 현재는 `clipboard_set_text("")`로 우회
  - 더 엄격한 감지가 필요하면 `clipboard.py` sentinel 방식도 고려 가능

- **Selectors 변화**
  - ECM UI DOM이 조금만 바뀌어도 실패율이 급증할 수 있으니,
  - 가장 먼저 `selectors.py`와 `ecm.py`의 wait/click 조건을 점검하는 것이 정석입니다.
