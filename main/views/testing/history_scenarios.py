# -*- coding: utf-8 -*-
import os, re, pathlib, asyncio, subprocess
from playwright.async_api import Page, expect, TimeoutError as PWTimeout, Locator
from typing import Pattern

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
    """
    앞/뒤가 '한글·영문·숫자'가 아니면 경계로 간주.
    (?<!…)(?!…) 대신 (^|[^…]) … ([^…]|$) 패턴으로 교체 → 브라우저 RegExp 호환↑
    """
    cls = r"0-9A-Za-z가-힣"
    return re.compile(rf"(?:^|[^{cls}]){re.escape(text)}(?:[^{cls}]|$)")

def _testno_pat(test_no: str) -> Pattern:
    """
    시험번호의 구분자(하이픈/언더스코어/공백/일부 유니코드 하이픈)를 서로 치환 가능하게 허용.
    ex) 'GS-B-25-0088' ↔ 'GS_B_25_0088' ↔ 'GS B 25 0088'
    """
    # 입력을 구분자로 토큰화
    tokens = [t for t in re.split(r"[-_\s\u2010-\u2015\u2212]+", test_no) if t]
    if not tokens:
        # 매칭 불가한 빈 입력 방어
        return re.compile(r"$^")  # never match

    # 허용 구분자 클래스: 공백/언더스코어/일반-및-유니코드 하이픈들
    sep = r"[\s_\-\u2010-\u2015\u2212]+"

    # 토큰 사이를 'sep'로 연결한 코어 패턴
    core = sep.join(map(re.escape, tokens))

    # 경계 래핑(시험번호 앞뒤가 글자/숫자/한글이 아닌 경우만)
    cls = r"0-9A-Za-z가-힣"
    pat = rf"(?:^|[^{cls}]){core}(?:[^{cls}]|$)"
    return re.compile(pat, re.IGNORECASE)

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
async def _try_click_doc_name_span(page: Page, 시험번호: str, timeout=15000, debug=False) -> bool:
    CSS_EVT = "span.document-list-item-name-text-span.left.hcursor.ellipsis[events='document-list-viewDocument-click']"
    CSS_SP  = "span.document-list-item-name-text-span.left.hcursor.ellipsis"
    pat_score = _boundary_pat("시험성적서")
    pat_num   = _testno_pat(시험번호) if 시험번호 else None

    async def _click(loc: Locator, tag: str) -> bool:
        if await loc.count() == 0:
            return False
        cand = loc.first
        if debug:
            try: print(f"[match:{tag}] {await cand.inner_text()!r}")
            except: pass
        try: await cand.scroll_into_view_if_needed()
        except: pass
        await expect(cand).to_be_visible(timeout=timeout)
        try:
            await cand.click()
        except Exception:
            try:    await cand.click(force=True)
            except Exception:
                await cand.evaluate("el => el.click()")
        # pane-2 등장까지 대기(네트워크 idle 대신 UI 시그널)
        await page.wait_for_function(
            """() => {
                const p = document.querySelector('#edm-contents-pane-2');
                if (!p) return false;
                const cs = getComputedStyle(p);
                const v = cs.display !== 'none' && cs.visibility !== 'hidden' && p.offsetParent !== null;
                return v && (p.querySelector('#prop-view-file-list-tbody') || p.querySelector('input.file-list-type'));
            }""",
            timeout=15000
        )
        return True

    # 1차: 스팬 직접 필터 (페이지 + 모든 프레임)
    scopes = [page] + list(page.frames)
    for scope in scopes:
        base = scope.locator(CSS_EVT)
        if await base.count() == 0:
            base = scope.locator(CSS_SP)

        # ① '시험성적서' 경계일치 먼저
        if await _click(base.filter(has_text=pat_score), "score-boundary"):
            return True
        # ② 시험번호 경계일치
        if pat_num and await _click(base.filter(has_text=pat_num), "num-boundary"):
            return True

    # 2차 폴백: **행(tr)** 단위로 필터 → 행 안의 스팬 클릭
    #   스팬 텍스트가 분할되었거나 prefix/suffix가 많은 경우를 커버
    for scope in scopes:
        rows = scope.locator("tr:has(span.document-list-item-name-text-span.left.hcursor.ellipsis)")
        # ① '시험성적서' 경계일치 행
        row = rows.filter(has_text=pat_score).first
        if await row.count() > 0:
            return await _click(row.locator(CSS_SP).first, "row-score-boundary")
        # ② 시험번호 경계일치 행
        if pat_num:
            row = rows.filter(has_text=pat_num).first
            if await row.count() > 0:
                return await _click(row.locator(CSS_SP).first, "row-num-boundary")

    if debug:
        # 상황 파악용 최소 덤프
        try:
            cands = page.locator(CSS_SP)
            n = await cands.count()
            texts = []
            for i in range(min(n, 8)):
                try: texts.append(await cands.nth(i).inner_text())
                except: break
            print(f"[info] span candidates={n}, samples={texts}")
        except: pass

    return False

async def _get_pane2(page: Page, timeout=T_MED) -> Locator:
    # pane-2가 열리고 내부에 리스트/체크박스가 나타날 때까지 UI 시그널로 대기
    await _wait_pane2_ready(page, timeout=timeout)

    pane2 = page.locator(SEL["pane2"])
    await expect(pane2).to_be_visible(timeout=timeout)

    # ⛳ Locator에는 wait_for_selector가 없음 → 하위 Locator로 잡고 wait_for(state=...)
    inner = pane2.locator(f"{SEL['file_tbody']}, input.file-list-type")
    await inner.first.wait_for(state="attached", timeout=timeout)
    # 또는: await expect(inner.first).to_be_attached(timeout=timeout)

    return pane2


async def _find_target_row(scope, 시험번호: str):
    """여러 전략으로 대상 행을 찾는다 (filename/title/data-filename/텍스트 폴백)"""
    tbody = scope.locator("#prop-view-file-list-tbody")
    await expect(tbody).to_be_visible(timeout=15000)

    # ★ 언더스코어 변형 추가
    alt_no = (시험번호 or "").replace("-", "_")

    # 1) 속성 기반(AND) — 원본 시험번호 + 언더스코어 변형 둘 다 시도
    strategies = [
        # filename/title/data-filename 속성에 '시험번호'와 '시험성적서'가 동시에 들어있는 tr
        f'tr[filename*="{시험번호}"][filename*="시험성적서"]',
        f'tr[title*="{시험번호}"][title*="시험성적서"]',
        f'tr[data-filename*="{시험번호}"][data-filename*="시험성적서"]',

        # ★ 언더스코어 변형
        f'tr[filename*="{alt_no}"][filename*="시험성적서"]',
        f'tr[title*="{alt_no}"][title*="시험성적서"]',
        f'tr[data-filename*="{alt_no}"][data-filename*="시험성적서"]',

        # 2) :has()로 자식 td 속성 매칭 (원본 + 언더스코어 변형)
        f'tr:has(td[filename*="{시험번호}"]):has(td[filename*="시험성적서"])',
        f'tr:has(td[title*="{시험번호}"]):has(td[title*="시험성적서"])',
        f'tr:has(td[filename*="{alt_no}"]):has(td[filename*="시험성적서"])',
        f'tr:has(td[title*="{alt_no}"]):has(td[title*="시험성적서"])',

        # 3) 텍스트 폴백은 아래에서 처리 (여기선 자리표시자)
        None,
    ]

    for sel in strategies:
        if sel:
            row = tbody.locator(sel).first
            if await row.count() > 0:
                return row

    # 3) 텍스트 기반 폴백 — 시험번호는 유연 매칭(_testno_pat), 성적서는 경계 매칭
    row = (
        tbody.locator("tr")
        .filter(has_text=_testno_pat(시험번호))
        .filter(has_text=_boundary_pat("시험성적서"))
        .first
    )
    if await row.count() > 0:
        return row

    return None


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
