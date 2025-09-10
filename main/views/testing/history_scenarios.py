# -*- coding: utf-8 -*-
import os, re, pathlib
import asyncio
from playwright.async_api import Page, expect, TimeoutError as PWTimeout, Error as PWError

BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
LOGIN_ID    = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW    = os.getenv("LOGIN_PW", "12sqec34!")
COPY_BTN_FULL_XPATH = os.getenv(
    "COPY_BTN_XPATH",
    "/html/body/div[2]/div[3]/div[2]/div[1]/div[4]/div/div/div[2]/div[2]/div[1]/div[2]/table/tbody/tr/td[1]/div[4]"
)

LEFT_TREE_SEL = (
    "div.edm-left-panel-menu-sub-item.ui-accordion-content.ui-helper-reset."
    "ui-widget-content.ui-corner-bottom.ui-accordion-content-active[submenu_type='Folder']"
)

async def _wait_login_completed(page: Page, timeout=30000):
    await page.wait_for_function(
        """
        () => {
          const notLoginURL = !/\\/auth\\/login/i.test(location.href);
          const form = document.querySelector('#form-login');
          const gone = !form || form.offsetParent === null || getComputedStyle(form).display === 'none';
          const bodyChanged = document.body && document.body.id !== 'login';
          return notLoginURL || gone || bodyChanged;
        }
        """,
        timeout=timeout,
    )

async def _ensure_logged_in(page: Page):
    await page.goto(f"{BASE_ORIGIN}/", wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    if "login" in page.url.lower() or await page.locator("#form-login").count() > 0:
        user = page.locator("input[name='user_id']")
        pwd  = page.locator("input[name='password']")
        await expect(user).to_be_visible(timeout=15000)
        await expect(pwd).to_be_visible(timeout=15000)
        await user.fill(LOGIN_ID); await pwd.fill(LOGIN_PW)
        btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
        await expect(btn).to_be_visible(timeout=10000)
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                await btn.click()
        except PWTimeout:
            await btn.click(); await page.wait_for_load_state("networkidle")
        await _wait_login_completed(page, timeout=30000)

async def _tree_click_by_name_contains(scope, text: str, timeout=15000):
    link = scope.locator(f"a[name*='{text}']").first
    await expect(link).to_be_visible(timeout=timeout)
    await link.click()

async def _find_filelist_scope(page: Page, timeout=30000):
    """#prop-view-file-list-tbody 가 있는 컨텍스트(Page or Frame)를 찾아 반환"""
    try:
        await page.wait_for_selector("#prop-view-file-list-tbody", timeout=timeout, state="attached")
        return page
    except Exception:
        pass
    for fr in page.frames:
        try:
            await fr.wait_for_selector("#prop-view-file-list-tbody", timeout=1000, state="attached")
            return fr
        except Exception:
            continue
    raise TimeoutError("파일 목록 tbody(#prop-view-file-list-tbody)가 나타나지 않았습니다.")

async def _dump_rows_for_debug(scope, job_dir: pathlib.Path):
    """행을 못 찾을 때 디버깅용으로 일부 행의 텍스트/속성을 덤프"""
    try:
        rows = scope.locator("#prop-view-file-list-tbody tr")
        count = await rows.count()
        lines = [f"[rows={count}]"]
        n = min(count, 20)
        for i in range(n):
            row = rows.nth(i)
            txt = (await row.inner_text()).strip().replace("\n", " / ")
            # 자주 쓰일 법한 속성만 샘플링
            attrs = await row.evaluate("""(el) => {
                const pick = k => el.getAttribute(k) || '';
                return {
                  filename: pick('filename'),
                  title: pick('title'),
                  'data-filename': pick('data-filename'),
                  'aria-label': pick('aria-label')
                };
            }""")
            lines.append(f"#{i} | {attrs} | {txt}")
        (job_dir / "filelist_dump.txt").write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass

async def _find_target_row(scope, 시험번호: str):
    """여러 전략으로 대상 행을 찾는다 (filename/title/data-filename/텍스트 폴백)"""
    tbody = scope.locator("#prop-view-file-list-tbody")
    await expect(tbody).to_be_visible(timeout=30000)

    # 1) 가장 강한: 동일 tr에 2개 속성 동시 포함
    strategies = [
        f'tr[filename*="{시험번호}"][filename*="시험성적서"]',
        f'tr[title*="{시험번호}"][title*="시험성적서"]',
        f'tr[data-filename*="{시험번호}"][data-filename*="시험성적서"]',
        # 2) :has()로 자식 td 속성 매칭
        f'tr:has(td[filename*="{시험번호}"]):has(td[filename*="시험성적서"])',
        f'tr:has(td[title*="{시험번호}"]):has(td[title*="시험성적서"])',
        # 3) 텍스트 동시 포함 (AND)
        None,  # 자리표시자: 아래에서 filter(has_text=...) 사용
    ]

    for sel in strategies:
        if sel:
            row = tbody.locator(sel).first
            if await row.count() > 0:
                return row

    # 텍스트 폴백 (어떤 칸에 있든 둘 다 텍스트로 포함)
    row = tbody.locator("tr").filter(has_text=시험번호).filter(has_text="시험성적서").first
    if await row.count() > 0:
        return row

    return None

# 페이지/프레임 어디에 있든 문서명 span을 찾아 클릭
async def _try_click_doc_name_span(page: Page, 시험번호: str, timeout=10000) -> bool:
    """
    span.document-list-item-name-text-span.left.hcursor.ellipsis 을 클릭한다.
    - 우선순위: has_text(시험번호) > has_text('시험성적서') > 첫 번째 항목
    - 페이지에서 못 찾으면 모든 iframe에서 탐색
    - 찾지 못해도 비치명적(False 리턴) → 이후 단계 진행
    """
    css = "span.document-list-item-name-text-span.left.hcursor.ellipsis"

    # 1) 메인 페이지
    loc = page.locator(css)
    if await loc.count() == 0:
        # 2) 프레임 순회
        for fr in page.frames:
            frloc = fr.locator(css)
            if await frloc.count() > 0:
                loc = frloc
                break

    if await loc.count() == 0:
        return False

    # 우선순위 선택
    cand = loc.filter(has_text=시험번호).first
    if await cand.count() == 0:
        cand = loc.filter(has_text="시험성적서").first
    if await cand.count() == 0:
        cand = loc.first

    try:
        await expect(cand).to_be_visible(timeout=timeout)
        await cand.click()
        # 클릭으로 상세/리스트가 갱신될 수 있으니 잠깐 대기
        await page.wait_for_load_state("networkidle")
        return True
    except Exception:
        return False

# 모든 페이지/프레임을 순회하는 제너레이터
def _all_scopes(page: Page):
    yield page
    for fr in page.frames:
        yield fr

# 복사 스니퍼: writeText/execCommand/copy 이벤트를 가로채 마지막 복사 본문을 보관
async def _prime_copy_sniffer(page: Page):
    inject_js = r"""
(() => {
  try {
    // 보관 버퍼
    window.__copied_texts = window.__copied_texts || [];
    const push = (t) => {
      try {
        if (typeof t === 'string' && t.trim()) {
          window.__last_copied = t;
          window.__copied_texts.push(t);
        }
      } catch (e) {}
    };

    // navigator.clipboard.writeText 훅킹
    if (navigator.clipboard && navigator.clipboard.writeText && !navigator.clipboard.__pw_hooked) {
      const _origWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = async (t) => {
        try { push(t); } catch(e) {}
        return _origWrite(t);
      };
      navigator.clipboard.__pw_hooked = true;
    }

    // document.execCommand('copy') 훅킹
    if (!document.__exec_copy_hooked) {
      const _origExec = document.execCommand.bind(document);
      document.execCommand = function(cmd, ui, value) {
        if (String(cmd || '').toLowerCase() === 'copy') {
          try {
            // value, selection, activeElement.value 등 후보를 모두 보관
            if (value) push(String(value));
            const sel = document.getSelection && document.getSelection();
            if (sel && sel.toString()) push(sel.toString());
            const el = document.activeElement;
            if (el && 'value' in el && el.value) push(el.value);
          } catch(e) {}
        }
        return _origExec(cmd, ui, value);
      };
      document.__exec_copy_hooked = true;
    }

    // copy 이벤트에서 clipboardData 읽기
    if (!document.__copy_evt_hooked) {
      document.addEventListener('copy', (e) => {
        try {
          const dt = e.clipboardData;
          if (dt) {
            const t = dt.getData('text/plain');
            if (t) push(t);
          }
        } catch(e) {}
      }, true);
      document.__copy_evt_hooked = true;
    }
  } catch (e) {}
})();
"""
    # 모든 스코프에 주입
    for scope in _all_scopes(page):
        try:
            await scope.add_init_script(inject_js)  # 이후 로드에도 적용
        except Exception:
            pass
        try:
            await scope.evaluate(inject_js)         # 현재 문서에도 즉시 적용
        except Exception:
            pass

# 복사 버튼 찾기 (XPATH 최우선, 안 되면 기존 셀렉터 폴백)
async def _find_copy_button(page: Page, timeout=15000):
    now = asyncio.get_running_loop().time
    deadline = now() + (timeout / 1000.0)

    # 1) full XPATH
    if COPY_BTN_FULL_XPATH:
        while now() < deadline:
            for scope in _all_scopes(page):
                try:
                    loc = scope.locator(f"xpath={COPY_BTN_FULL_XPATH}")
                    await loc.wait_for(state="attached", timeout=500)
                    if await loc.is_visible():
                        return loc
                except Exception:
                    pass
            await page.wait_for_timeout(150)

    # 2) 폴백 셀렉터들
    selectors = [
        "div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor",
        "#prop-view-document-btn-url-copy",
        "div.prop-view-file-btn-internal-urlcopy[events='document-internal-url-click']",
        "div[events='document-internal-url-click']",
    ]
    while now() < deadline:
        for scope in _all_scopes(page):
            for sel in selectors:
                loc = scope.locator(sel)
                try:
                    await loc.first.wait_for(state="attached", timeout=400)
                    if await loc.first.is_visible():
                        return loc.first
                except Exception:
                    continue
        await page.wait_for_timeout(150)

    raise RuntimeError("URL 복사 버튼을 찾지 못했습니다(XPATH 및 폴백 모두 실패).")

# 복사 버튼 '확실히' 클릭(+ 알림/모달 처리)
async def _click_copy_and_get_message(page: Page, btn, timeout=4000) -> str:
    # 클릭 시도
    try:
        await btn.scroll_into_view_if_needed()
        await expect(btn).to_be_visible(timeout=timeout)
        try:
            await btn.click()
        except Exception:
            await btn.click(force=True)
    except Exception:
        await btn.evaluate("(el) => el.click()")

    # 네이티브 alert() 메시지 캡처
    try:
        async with page.expect_event("dialog", timeout=1500) as di:
            pass
    except Exception:
        di = None

    if di:
        dlg = await di.value
        msg = (dlg.message or "").strip()
        try:
            await dlg.accept()
        except Exception:
            pass
        return msg

    # in-page 모달(jQuery UI 등) 텍스트 캡처
    try:
        modal = page.locator(".ui-dialog:visible .ui-dialog-content:visible")
        if await modal.count():
            txt = (await modal.first.inner_text()).strip()
            ok_btn = page.locator(".ui-dialog:visible .ui-dialog-buttonset button:has-text('확인')")
            if await ok_btn.count():
                try:
                    await ok_btn.first.click()
                except Exception:
                    pass
            return txt
    except Exception:
        pass

    return ""
    
# 복사된 텍스트 읽기 (클립보드 → 여러 입력 폴백)
async def _read_copied_text(page: Page) -> str:
    # 0) 스니퍼가 저장한 값 최우선
    for scope in _all_scopes(page):
        try:
            txt = await scope.evaluate("window.__last_copied || (window.__copied_texts && window.__copied_texts.slice(-1)[0]) || ''")
            if txt and txt.strip():
                return txt
        except Exception:
            pass

    # 1) 클립보드
    for scope in _all_scopes(page):
        try:
            txt = await scope.evaluate("navigator.clipboard.readText()")
            if txt and txt.strip():
                return txt
        except Exception:
            pass

    # 2) 입력 상자 폴백
    input_selectors = [
        "input#prop-view-document-internal-url",
        "input[name*='internal'][name*='url']",
        "input[type='text'][id*='internal'][id*='url']",
        "input[type='text'][name*='url']",
    ]
    for scope in _all_scopes(page):
        for sel in input_selectors:
            loc = scope.locator(sel)
            if await loc.count():
                try:
                    v = await loc.first.input_value()
                    if v and v.strip():
                        return v
                except Exception:
                    continue

    # 3) 화면 내 텍스트에서 URL 추출(최후의 수단)
    for scope in _all_scopes(page):
        try:
            candidates = await scope.evaluate(r"""
                () => {
                  const vals = [];
                  for (const el of document.querySelectorAll('a[href^="http"]')) {
                    vals.push(el.href);
                  }
                  for (const el of document.querySelectorAll('input[type="text"], textarea')) {
                    if (el.value) vals.push(el.value);
                  }
                  const it = document.createNodeIterator(document.body, NodeFilter.SHOW_TEXT);
                  let n; while (n = it.nextNode()) {
                    const t = n.nodeValue || '';
                    if (t && t.includes('http')) vals.push(t);
                  }
                  return vals.slice(0, 200);
                }
            """)
            for s in candidates:
                m = re.search(r"https?://[^\s]+", s)
                if m:
                    return m.group(0)
        except Exception:
            pass

    return ""

async def run_scenario_async(page: Page, job_dir: pathlib.Path, *, 시험번호: str, 연도: str, 날짜: str, **kwargs) -> str:
    assert 시험번호 and 연도 and 날짜, "필수 인자(시험번호/연도/날짜)가 비었습니다."
    job_dir.mkdir(parents=True, exist_ok=True)

    # 1) 접속/로그인
    await _ensure_logged_in(page)

    # 2) 좌측 트리
    left_tree = page.locator(LEFT_TREE_SEL)
    await expect(left_tree).to_be_visible(timeout=30000)

    # 3) 연도
    await _tree_click_by_name_contains(left_tree, 연도, timeout=20000)
    # 4) GS인증심의위원회
    await _tree_click_by_name_contains(left_tree, "GS인증심의위원회", timeout=20000)
    # 5) 날짜(YYYYMMDD)
    await _tree_click_by_name_contains(left_tree, 날짜, timeout=20000)
    # 6) 시험번호
    await _tree_click_by_name_contains(left_tree, 시험번호, timeout=20000)

    
    # 6.5) ★ 문서명 span 클릭 (요청하신 추가 스텝)
    clicked = await _try_click_doc_name_span(page, 시험번호, timeout=12000)
    if clicked:
        # 문서명 클릭 후 콘텐츠가 바뀌는 UI라면 안정화를 위해 한 번 더 대기
        await page.wait_for_load_state("networkidle")
        
    # 패널 로딩 대기 + 파일리스트 스코프 결정
    await page.wait_for_load_state("networkidle")
    try:
        scope = await _find_filelist_scope(page, timeout=20000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded")
        scope = await _find_filelist_scope(page, timeout=20000)

    # 7) 행 찾기(보강)
    row = await _find_target_row(scope, 시험번호)
    if not row:
        # 디버그 덤프 남기고 에러
        await _dump_rows_for_debug(scope, job_dir)
        raise RuntimeError(f'파일 목록에서 "{시험번호}" & "시험성적서"를 포함하는 행을 못 찾았습니다.')

    # 보이도록 스크롤 후 가시성 보장
    await row.scroll_into_view_if_needed()
    await expect(row).to_be_visible(timeout=20000)

    # 체크박스: 행 내부에서 가장 범용적인 선택
    checkbox = row.locator('input[type="checkbox"]')
    if await checkbox.count() == 0:
        # 기존 클래스명도 시도
        checkbox = row.locator('td.prop-view-file-list-item-checkbox input[type="checkbox"], input.file-list-type')
    await expect(checkbox.first).to_be_visible(timeout=10000)
    await checkbox.first.check(timeout=10000)

    # 8) (신규) 복사 스니퍼 주입
    await _prime_copy_sniffer(page)

    # 9) 내부 URL 복사 버튼 찾기 (XPATH 우선)
    copy_btn = await _find_copy_button(page, timeout=20000)

    # 10) 클릭하면서 메시지 캡처
    msg = await _click_copy_and_get_message(page, copy_btn, timeout=4000)

    # 11) 최종 텍스트 확보 (msg에 http 없으면 버리고 스니퍼/클립보드/폴백 사용)
    copied_text = ""
    if msg and re.search(r"https?://", msg):
        copied_text = msg.strip()
    else:
        copied_text = await _read_copied_text(page)

    if not copied_text:
        await page.screenshot(path=str(job_dir / "list_after_copy_fail.png"), full_page=True)
        raise RuntimeError("복사는 되었지만 텍스트를 읽지 못했습니다.")

    # 12) URL만 추출 (3번째 줄 우선 → 본문 내 최초 http → 페이지 전체 텍스트 폴백)
    url = ""
    lines = [ln.strip() for ln in copied_text.splitlines() if ln.strip()]
    if len(lines) >= 3 and lines[2].startswith(("http://", "https://")):
        url = lines[2]
    else:
        m = re.search(r"https?://[^\s]+", copied_text)
        url = m.group(0) if m else ""

    if not url:
        page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        m2 = re.search(r"https?://[^\s]+", page_text or "")
        url = m2.group(0) if m2 else ""

    if not url:
        # 디버깅을 위해 원문도 남겨둠
        (job_dir / "copied_raw.txt").write_text(copied_text, encoding="utf-8")
        await page.screenshot(path=str(job_dir / "url_extract_fail.png"), full_page=True)
        raise RuntimeError("복사는 되었지만 URL을 찾지 못했습니다.")

    # 콘솔 출력 및 산출물 저장
    await page.evaluate("(u) => console.log('EXTRACTED_URL:', u)", url)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    return url  # ← 최종적으로 URL만 반환 (final_link가 URL이 됨)
