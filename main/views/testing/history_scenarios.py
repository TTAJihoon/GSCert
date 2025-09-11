# -*- coding: utf-8 -*-
import os, re, pathlib, asyncio, subprocess
from playwright.async_api import Page, expect, TimeoutError as PWTimeout, Locator

# =========================
# Config & Constants
# =========================
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
LOGIN_ID    = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW    = os.getenv("LOGIN_PW", "12sqec34!")
DEBUG_PW    = os.getenv("PW_DEBUG", "0") == "1"   # 디버그 로그 on/off

# timeouts
T_SHORT = 5_000
T_MED   = 15_000
T_LONG  = 30_000

# selectors
SEL = {
    "left_tree": (
        "div.edm-left-panel-menu-sub-item.ui-accordion-content.ui-helper-reset."
        "ui-widget-content.ui-corner-bottom.ui-accordion-content-active[submenu_type='Folder']"
    ),
    "pane2": "#edm-contents-pane-2",
    "file_tbody": "#prop-view-file-list-tbody",
    "doc_span_evt": (
        "span.document-list-item-name-text-span.left.hcursor.ellipsis"
        "[events='document-list-viewDocument-click']"
    ),
    "doc_span": "span.document-list-item-name-text-span.left.hcursor.ellipsis",
    "copy_btns": [
        "div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor",
        "#prop-view-document-btn-url-copy",
        "div.prop-view-file-btn-internal-urlcopy[events='document-internal-url-click']",
        "div[events='document-internal-url-click']",
    ],
}

# (옵션) XPATH 우선 시도: 필요 없으면 env에서 비우세요.
COPY_BTN_FULL_XPATH = os.getenv("COPY_BTN_XPATH", "").strip()


# =========================
# Small Utilities
# =========================
def _boundary_pat(text: str) -> re.Pattern:
    """양쪽이 한글/영문/숫자가 아니면 경계로 간주(언더스코어/하이픈/점 등은 경계 인정)."""
    return re.compile(rf"(?<![0-9A-Za-z가-힣]){re.escape(text)}(?![0-9A-Za-z가-힣])")

async def _wait_top_ready(page: Page, timeout=T_MED):
    """로그인 완료 후 상단 컨테이너가 보이는지로 초기 안정화."""
    await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    await page.wait_for_function(
        """
        () => {
          const top = document.querySelector('#top-container');
          if (!top) return false;
          const cs = getComputedStyle(top);
          return cs.display !== 'none' && cs.visibility !== 'hidden';
        }
        """,
        timeout=timeout
    )

async def _wait_pane2_ready(page: Page, timeout=T_MED):
    """pane-2가 보이고 내부에 파일리스트 또는 체크박스가 나타날 때까지."""
    await page.wait_for_function(
        """
        () => {
          const pane = document.querySelector('#edm-contents-pane-2');
          if (!pane) return false;
          const cs = getComputedStyle(pane);
          const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && pane.offsetParent !== null;
          if (!visible) return false;
          return !!(pane.querySelector('#prop-view-file-list-tbody') ||
                    pane.querySelector('input.file-list-type'));
        }
        """,
        timeout=timeout
    )

def _all_scopes(page: Page):
    yield page
    for fr in page.frames:
        yield fr


# =========================
# Auth & Navigation
# =========================
async def _wait_login_completed(page: Page, timeout=T_LONG):
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
    # 로그인 폼 존재 시만 로그인
    if "login" in page.url.lower() or await page.locator("#form-login").count() > 0:
        user = page.locator("input[name='user_id']")
        pwd  = page.locator("input[name='password']")
        await expect(user).to_be_visible(timeout=T_MED)
        await expect(pwd).to_be_visible(timeout=T_MED)
        await user.fill(LOGIN_ID); await pwd.fill(LOGIN_PW)
        btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
        await expect(btn).to_be_visible(timeout=T_SHORT)
        try:
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=T_MED):
                await btn.click()
        except PWTimeout:
            await btn.click()
    await _wait_login_completed(page, timeout=T_LONG)
    await _wait_top_ready(page, timeout=T_MED)

async def _tree_click_by_name_contains(scope: Locator | Page, text: str, timeout=T_MED):
    link = scope.locator(f"a[name*='{text}']").first
    await expect(link).to_be_visible(timeout=timeout)
    await link.click()


# =========================
# Document selection
# =========================
async def _try_click_doc_name_span(page: Page, 시험번호: str, timeout=T_MED, debug=False) -> bool:
    """
    문서명 span 클릭 → pane-2 열림 확인.
    우선순위: ① '시험성적서' 경계일치 → ② {시험번호} 경계일치
    """
    pat_score = _boundary_pat("시험성적서")
    pat_num   = _boundary_pat(시험번호) if 시험번호 else None

    async def _click_first(loc, tag: str) -> bool:
        if await loc.count() == 0:
            return False
        cand = loc.first
        if debug or DEBUG_PW:
            try: print(f"[match:{tag}] {await cand.inner_text()!r}")
            except Exception: pass
        try: await cand.scroll_into_view_if_needed()
        except Exception: pass
        await expect(cand).to_be_visible(timeout=timeout)
        try:
            await cand.click()
        except Exception:
            try:    await cand.click(force=True)
            except Exception:
                await cand.evaluate("el => el.click()")
        await _wait_pane2_ready(page, timeout=T_MED)
        return True

    for scope in _all_scopes(page):
        base = scope.locator(SEL["doc_span_evt"])
        if await base.count() == 0:
            base = scope.locator(SEL["doc_span"])

        # ① '시험성적서' 경계일치
        if await _click_first(base.filter(has_text=pat_score), "score-boundary"):
            return True
        # ② {시험번호} 경계일치
        if pat_num and await _click_first(base.filter(has_text=pat_num), "num-boundary"):
            return True

    if debug or DEBUG_PW:
        print("[info] no clickable span matched by boundary rules ('시험성적서' → 시험번호)")
    return False

async def _get_pane2(page: Page, timeout=T_MED) -> Locator:
    await _wait_pane2_ready(page, timeout=timeout)
    pane2 = page.locator(SEL["pane2"])
    await expect(pane2).to_be_visible(timeout=timeout)
    # 파일리스트 존재 대기(둘 중 하나만 있어도 OK)
    await pane2.wait_for_selector(f"{SEL['file_tbody']}, input.file-list-type", timeout=timeout)
    return pane2

async def _find_target_row(scope: Locator, 시험번호: str) -> Locator | None:
    """pane-2(=scope) 내부에서 대상 행을 찾는다: 텍스트 AND 방식으로 단순화."""
    tbody = scope.locator(SEL["file_tbody"])
    await expect(tbody).to_be_visible(timeout=T_MED)
    row = tbody.locator("tr").filter(has_text=시험번호).filter(has_text="시험성적서").first
    return row if (await row.count() > 0) else None


# =========================
# Clipboard helpers
# =========================
async def _prime_copy_sniffer(page: Page):
    js = r"""
(() => {
  try {
    window.__copied_texts = window.__copied_texts || [];
    window.__copy_seq = window.__copy_seq || 0;
    const push = (t) => {
      try {
        if (typeof t === 'string' && t.trim()) {
          window.__last_copied = t;
          window.__copied_texts.push(t);
          window.__copy_seq = (window.__copy_seq || 0) + 1;
          window.__last_copied_at = Date.now();
        }
      } catch (e) {}
    };
    if (navigator.clipboard && navigator.clipboard.writeText && !navigator.clipboard.__pw_hooked) {
      const _origWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = async (t) => { try { push(t); } catch(e) {} return _origWrite(t); };
      navigator.clipboard.__pw_hooked = true;
    }
    if (!document.__exec_copy_hooked) {
      const _origExec = document.execCommand.bind(document);
      document.execCommand = function(cmd, ui, value) {
        if (String(cmd || '').toLowerCase() === 'copy') {
          try {
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
    for scope in _all_scopes(page):
        try: await scope.add_init_script(js)
        except Exception: pass
        try: await scope.evaluate(js)
        except Exception: pass

async def _get_copy_seq(page: Page) -> int:
    try: return await page.evaluate("() => window.__copy_seq || 0")
    except Exception: return 0

async def _wait_for_new_copy(page: Page, prev_seq: int, timeout_ms: int = 1500) -> bool:
    try:
        await page.wait_for_function("(prev) => (window.__copy_seq || 0) > prev", prev_seq, timeout=timeout_ms)
        return True
    except Exception:
        return False

async def _read_clipboard_via_paste(page: Page) -> str:
    try:
        await page.evaluate("""
          () => {
            let el = document.getElementById('__pw_clipboard_sink');
            if (!el) {
              el = document.createElement('textarea');
              el.id = '__pw_clipboard_sink';
              el.style.position = 'fixed';
              el.style.opacity = '0';
              el.style.pointerEvents = 'none';
              el.style.left = '-9999px';
              el.style.top = '0';
              document.body.appendChild(el);
            }
            el.value = ''; el.focus();
          }
        """)
        await page.keyboard.press("Control+V")  # (mac이면 Meta+V)
        await page.wait_for_timeout(80)
        return (await page.locator("#__pw_clipboard_sink").input_value() or "").strip()
    except Exception:
        return ""

def _read_os_clipboard_windows() -> str:
    try:
        ps = r"$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Clipboard -Raw"
        cp = subprocess.run(
            ["powershell", "-NoLogo", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", timeout=3
        )
        if cp.returncode == 0:
            out = cp.stdout.lstrip("\ufeff").replace("\r\n", "\n")
            return out.strip()
    except Exception:
        pass
    return ""

async def _click_copy_and_get_clipboard_text(page: Page, btn: Locator, *, retries: int = 10, wait_ms: int = 120) -> str:
    prev_seq = await _get_copy_seq(page)
    try:
        prev_os = await asyncio.to_thread(_read_os_clipboard_windows)
    except Exception:
        prev_os = ""

    try:
        await btn.scroll_into_view_if_needed()
        await expect(btn).to_be_visible(timeout=T_SHORT)
        try:    await btn.click()
        except Exception:
            await btn.click(force=True)
    except Exception:
        await btn.evaluate("(el) => el.click()")

    await _wait_for_new_copy(page, prev_seq, timeout_ms=1500)

    for i in range(retries):
        try:
            seq = await _get_copy_seq(page)
            if seq > prev_seq:
                t = await page.evaluate("() => window.__last_copied || ''")
                if t and t.strip():
                    return t.strip()
        except Exception:
            pass

        try:
            t = await _read_clipboard_via_paste(page)
            if t and t.strip() and t != prev_os:
                return t.strip()
        except Exception:
            pass

        try:
            cur_os = await asyncio.to_thread(_read_os_clipboard_windows)
            if cur_os and cur_os.strip() and cur_os != prev_os:
                return cur_os.strip()
        except Exception:
            pass

        try:
            for scope in _all_scopes(page):
                try:
                    nav_t = await scope.evaluate("navigator.clipboard.readText()")
                    if nav_t and nav_t.strip() and nav_t != prev_os:
                        return nav_t.strip()
                except Exception:
                    continue
        except Exception:
            pass

        await page.wait_for_timeout(wait_ms * (i + 1))
    return ""


# =========================
# Copy button find
# =========================
async def _find_copy_button(page: Page, timeout=T_MED) -> Locator:
    deadline = asyncio.get_running_loop().time() + (timeout / 1000.0)

    # 1) XPATH (옵션)
    if COPY_BTN_FULL_XPATH:
        while asyncio.get_running_loop().time() < deadline:
            for scope in _all_scopes(page):
                try:
                    loc = scope.locator(f"xpath={COPY_BTN_FULL_XPATH}")
                    await loc.wait_for(state="attached", timeout=300)
                    if await loc.is_visible():
                        return loc
                except Exception:
                    pass
            await page.wait_for_timeout(120)

    # 2) 셀렉터 폴백
    while asyncio.get_running_loop().time() < deadline:
        for scope in _all_scopes(page):
            for sel in SEL["copy_btns"]:
                loc = scope.locator(sel).first
                try:
                    await loc.wait_for(state="attached", timeout=250)
                    if await loc.is_visible():
                        return loc
                except Exception:
                    continue
        await page.wait_for_timeout(120)

    raise RuntimeError("URL 복사 버튼을 찾지 못했습니다.")


# =========================
# URL extraction
# =========================
def _extract_url_fuzzy(text: str) -> str:
    cleaned = re.sub(r"[\u200b\u200c\u200d\u2060]", "", text or "").replace("\xa0", " ")
    m = re.search(r"https?://[^\s<>'\"()\[\]]+", cleaned, re.IGNORECASE)
    if m:
        return m.group(0)
    spaced = re.sub(r"\s+", " ", cleaned)
    m2 = re.search(r"h\s*t\s*t\s*p\s*(s?)\s*:\s*/\s*/\s*([^\s<>'\"()\[\]]+)", spaced, re.IGNORECASE)
    if m2:
        scheme = "https" if m2.group(1) else "http"
        rest = re.sub(r"\s+", "", m2.group(2))
        return f"{scheme}://{rest}"
    return ""


# =========================
# Scenario runner (public)
# =========================
async def run_scenario_async(page: Page, job_dir: pathlib.Path, *, 시험번호: str, 연도: str, 날짜: str, **kwargs) -> str:
    assert 시험번호 and 연도 and 날짜, "필수 인자(시험번호/연도/날짜)가 비었습니다."
    job_dir.mkdir(parents=True, exist_ok=True)

    # 1) 접속/로그인
    await _ensure_logged_in(page)

    # 2) 좌측 트리 선택
    left_tree = page.locator(SEL["left_tree"])
    await expect(left_tree).to_be_visible(timeout=T_MED)
    await _tree_click_by_name_contains(left_tree, 연도, timeout=T_SHORT)
    await _tree_click_by_name_contains(left_tree, "GS인증심의위원회", timeout=T_SHORT)
    await _tree_click_by_name_contains(left_tree, 날짜, timeout=T_SHORT)
    await _tree_click_by_name_contains(left_tree, 시험번호, timeout=T_SHORT)

    # 3) 문서명 span 클릭 (우선순위: '시험성적서' → 시험번호)
    clicked = await _try_click_doc_name_span(page, 시험번호, timeout=T_MED, debug=DEBUG_PW)
    if not clicked:
        raise RuntimeError("목록에서 클릭할 문서명을 찾지 못했습니다.")

    # 4) pane-2 기준 스코프
    pane2 = await _get_pane2(page, timeout=T_MED)

    # 5) 행 찾기 (텍스트 AND)
    row = await _find_target_row(pane2, 시험번호)
    if not row:
        raise RuntimeError(f'파일 목록에서 "{시험번호}" & "시험성적서"를 포함하는 행을 못 찾았습니다.')

    # 6) 체크박스 체크
    await row.scroll_into_view_if_needed()
    await expect(row).to_be_visible(timeout=T_MED)
    checkbox = row.locator('input[type="checkbox"], input.file-list-type').first
    await expect(checkbox).to_be_visible(timeout=T_MED)
    await checkbox.check(timeout=T_MED)

    # 7) 복사 스니퍼 주입 → 버튼 찾기 → 클릭 & 텍스트 읽기
    await _prime_copy_sniffer(page)
    copy_btn = await _find_copy_button(page, timeout=T_MED)
    copied_text = await _click_copy_and_get_clipboard_text(page, copy_btn, retries=10, wait_ms=120)
    if not copied_text:
        await page.screenshot(path=str(job_dir / "url_extract_fail.png"), full_page=True)
        raise RuntimeError("복사는 되었지만 텍스트를 읽지 못했습니다.")

    # 8) URL 추출
    url = _extract_url_fuzzy(copied_text) or copied_text.strip()

    # 9) 산출물
    try:
        await page.evaluate("(u) => console.log('EXTRACTED_URL:', u)", url)
    except Exception:
        pass
    await page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")
    return url
