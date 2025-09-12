# -*- coding: utf-8 -*-
import os, re, pathlib, asyncio, subprocess
from typing import Optional, Pattern

from playwright.async_api import Page, expect, TimeoutError as PWTimeout, Error as PWError, Locator

# ────────────────────────────────────────────────────────────
# 상수/셀렉터/타임아웃
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")

LEFT_TREE_SEL = (
    "div.edm-left-panel-menu-sub-item.ui-accordion-content.ui-helper-reset."
    "ui-widget-content.ui-corner-bottom.ui-accordion-content-active[submenu_type='Folder']"
)

# 문서 스팬(목록)
DOC_SPAN_CSS = "span.document-list-item-name-text-span.left.hcursor.ellipsis"

# 복사 버튼 XPath (환경변수로 덮어쓰기 가능)
COPY_BTN_FULL_XPATH = os.getenv(
    "COPY_BTN_XPATH",
    "/html/body/div[2]/div[3]/div[2]/div[1]/div[4]/div/div/div[2]/div[2]/div[1]/div[2]/table/tbody/tr/td[1]/div[4]"
)

# 타임아웃(밀리초)
T_SHORT = 6_000
T_MED   = 12_000
T_LONG  = 25_000

SEL = {
    "left_tree": LEFT_TREE_SEL,
    "doc_span":  DOC_SPAN_CSS,
    "file_tbody": "#prop-view-file-list-tbody",
}

# ────────────────────────────────────────────────────────────
# 정규식 유틸: 경계/시험번호 유연 매칭
def _boundary_pat(text: str) -> Pattern:
    """
    앞/뒤가 '한글·영문·숫자'가 아니면 경계로 간주.
    (^|[^…]) … ([^…]|$) 패턴으로 브라우저 RegExp와 호환.
    """
    cls = r"0-9A-Za-z가-힣"
    return re.compile(rf"(?:^|[^{cls}]){re.escape(text)}(?:[^{cls}]|$)")

def _testno_pat(test_no: str) -> Pattern:
    """
    시험번호의 구분자(하이픈/언더스코어/공백/유니코드 하이픈)를 상호 치환 가능하게 허용.
    ex) 'GS-B-25-0088' ↔ 'GS_B_25_0088' ↔ 'GS B 25 0088'
    """
    tokens = [t for t in re.split(r"[-_\s\u2010-\u2015\u2212]+", test_no or "") if t]
    if not tokens:
        return re.compile(r"$^")  # never match
    sep = r"[\s_\-\u2010-\u2015\u2212]+"
    core = sep.join(map(re.escape, tokens))
    cls = r"0-9A-Za-z가-힣"
    pat = rf"(?:^|[^{cls}]){core}(?:[^{cls}]|$)"
    return re.compile(pat, re.IGNORECASE)

# ────────────────────────────────────────────────────────────
# 디버깅 보조
async def _dump_locator(locator: Locator, label: str, max_items: int = 5, pattern: Optional[Pattern] = None) -> None:
    try:
        cnt = await locator.count()
        print(f"\n[{label}] count={cnt}")
        take = min(cnt, max_items)
        for i in range(take):
            el = locator.nth(i)
            inner = await el.inner_text()
            raw = await el.evaluate("el => el.textContent")
            html = await el.evaluate("el => el.outerHTML")
            match_inner = bool(pattern.search(inner)) if pattern else None
            match_raw = bool(pattern.search(raw)) if pattern else None
            print(f"--- {label}[{i}] ---")
            print(f"inner_text: {inner!r}")
            print(f"textContent: {raw!r}")
            if pattern:
                print(f"regex match(inner_text)={match_inner}, regex match(textContent)={match_raw}")
            print(f"outerHTML(head): {html[:400]}")
    except Exception:
        pass

# ────────────────────────────────────────────────────────────
# 공통 유틸
async def _tree_click_by_name_contains(scope: Page | Locator, text: str, timeout=T_SHORT):
    link = scope.locator(f"a[name*='{text}']").first
    await expect(link).to_be_visible(timeout=timeout)
    await link.click()

def _all_scopes(page: Page):
    yield page
    for fr in page.frames:
        yield fr

# ────────────────────────────────────────────────────────────
# 파일 리스트 tbody가 있는 컨텍스트 찾기
async def _find_filelist_scope(page: Page, timeout=T_LONG) -> Page:
    try:
        await page.wait_for_selector(SEL["file_tbody"], timeout=timeout, state="attached")
        return page
    except Exception:
        pass
    for fr in page.frames:
        try:
            await fr.wait_for_selector(SEL["file_tbody"], timeout=1_000, state="attached")
            return fr
        except Exception:
            continue
    raise TimeoutError("파일 목록 tbody(#prop-view-file-list-tbody)가 나타나지 않았습니다.")

async def _dump_rows_for_debug(scope: Page, job_dir: pathlib.Path):
    """행을 못 찾을 때 디버깅용으로 일부 행의 텍스트/속성을 덤프"""
    try:
        rows = scope.locator("#prop-view-file-list-tbody tr")
        count = await rows.count()
        lines = [f"[rows={count}]"]
        n = min(count, 20)
        for i in range(n):
            row = rows.nth(i)
            txt = (await row.inner_text()).strip().replace("\n", " / ")
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

# ────────────────────────────────────────────────────────────
# 행 찾기: 속성 + 텍스트 혼합 전략 (시험성적서 AND 시험번호 유연 매칭)
async def _find_target_row(scope: Page, 시험번호: str):
    tbody = scope.locator("#prop-view-file-list-tbody")
    await expect(tbody).to_be_visible(timeout=T_MED)

    alt_no = (시험번호 or "").replace("-", "_")

    strategies = [
        # 속성 AND 매칭(원본/언더스코어 변형)
        f'tr[filename*="{시험번호}"][filename*="시험성적서"]',
        f'tr[title*="{시험번호}"][title*="시험성적서"]',
        f'tr[data-filename*="{시험번호}"][data-filename*="시험성적서"]',
        f'tr[filename*="{alt_no}"][filename*="시험성적서"]',
        f'tr[title*="{alt_no}"][title*="시험성적서"]',
        f'tr[data-filename*="{alt_no}"][data-filename*="시험성적서"]',

        # 자식 td 속성 매칭
        f'tr:has(td[filename*="{시험번호}"]):has(td[filename*="시험성적서"])',
        f'tr:has(td[title*="{시험번호}"]):has(td[title*="시험성적서"])',
        f'tr:has(td[filename*="{alt_no}"]):has(td[filename*="시험성적서"])',
        f'tr:has(td[title*="{alt_no}"]):has(td[title*="시험성적서"])',

        # 텍스트 폴백은 아래에서 처리
        None,
    ]

    for sel in strategies:
        if sel:
            row = tbody.locator(sel).first
            if await row.count() > 0:
                return row

    # 텍스트 폴백: 시험번호 유연 매칭 + '시험성적서' 경계 매칭
    row = (
        tbody.locator("tr")
        .filter(has_text=_testno_pat(시험번호))
        .filter(has_text=_boundary_pat("시험성적서"))
        .first
    )
    if await row.count() > 0:
        return row

    return None

# ────────────────────────────────────────────────────────────
# 문서명 스팬 클릭: '시험성적서' 경계일치 우선 → 시험번호(완전일치 또는 유연 매칭)
async def _try_click_doc_name_span(page: Page, 시험번호: str, timeout=T_MED, debug=False) -> bool:
    CSS = DOC_SPAN_CSS
    scopes = [page] + list(page.frames)

    # 1) '시험성적서' 경계 일치 우선
    pat_score = _boundary_pat("시험성적서")

    for idx, scope in enumerate(scopes):
        base = scope.locator(CSS)
        fall = base.filter(has_text=pat_score)

        if debug:
            await _dump_locator(base, f"scope {idx} BASE(all spans)", max_items=5)
            await _dump_locator(fall, f"scope {idx} FILTER('시험성적서'-boundary)", max_items=5, pattern=pat_score)

        if await fall.count():
            cand = fall.first
            # ★ 전면 포커스 보장
            try: await page.bring_to_front()
            except Exception: pass

            await expect(cand).to_be_visible(timeout=timeout)
            await cand.click()
            # pane-2 오픈은 run_scenario_async에서 별도 시그널로 확인
            return True

    # 2) 시험번호: 먼저 '완전 일치', 없으면 유연 매칭(_testno_pat)
    exact_pat = re.compile(rf"^\s*{re.escape(시험번호)}\s*$") if 시험번호 else None
    flex_pat  = _testno_pat(시험번호) if 시험번호 else None

    for idx, scope in enumerate(scopes):
        base = scope.locator(CSS)
        cand = base
        if exact_pat:
            cand = cand.filter(has_text=exact_pat)
        if await cand.count() == 0 and flex_pat:
            cand = base.filter(has_text=flex_pat)

        if debug:
            await _dump_locator(base,  f"scope {idx} BASE(all spans)", max_items=5)
            if exact_pat:
                await _dump_locator(base.filter(has_text=exact_pat), f"scope {idx} FILTER(exact test-no)", max_items=5, pattern=exact_pat)
            if flex_pat:
                await _dump_locator(base.filter(has_text=flex_pat), f"scope {idx} FILTER(flex test-no)", max_items=5, pattern=flex_pat)

        if await cand.count():
            target = cand.first
            try: await page.bring_to_front()
            except Exception: pass

            await expect(target).to_be_visible(timeout=timeout)
            await target.click()
            return True

    if debug:
        print("[info] no match for '시험성적서'(boundary) or test-no(exact/flex)")
    return False

# ────────────────────────────────────────────────────────────
# 클립보드/복사
async def _get_copy_seq(page: Page) -> int:
    try:
        return await page.evaluate("() => window.__copy_seq || 0")
    except Exception:
        return 0

async def _get_copy_seq_any(page: Page) -> int:
    """모든 프레임의 __copy_seq 중 최대값을 반환"""
    mx = 0
    for scope in _all_scopes(page):
        try:
            v = await scope.evaluate("() => window.__copy_seq || 0")
            mx = max(mx, int(v or 0))
        except Exception:
            continue
    return mx

async def _wait_for_new_copy_any(page: Page, prev_seq: int, timeout_ms: int = 1_500) -> bool:
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)
    while asyncio.get_running_loop().time() < deadline:
        try:
            if (await _get_copy_seq_any(page)) > prev_seq:
                return True
        except Exception:
            pass
        await page.wait_for_timeout(80)
    return False

async def _prime_copy_sniffer(page: Page):
    inject_js = r"""
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
    # 모든 스코프에 주입
    for scope in _all_scopes(page):
        try:
            await scope.add_init_script(inject_js)
        except Exception:
            pass
        try:
            await scope.evaluate(inject_js)
        except Exception:
            pass

async def _find_copy_button(page: Page, timeout=T_MED):
    now = asyncio.get_running_loop().time
    deadline = now() + (timeout / 1000.0)

    # 1) XPath 최우선
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
            await page.wait_for_timeout(120)

    # 2) 폴백 셀렉터
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
        await page.wait_for_timeout(120)

    raise RuntimeError("URL 복사 버튼을 찾지 못했습니다(XPATH 및 폴백 모두 실패).")

async def _read_clipboard_via_paste(page: Page) -> str:
    try:
        await page.evaluate("""
          () => {
            let el = document.getElementById('__pw_clipboard_sink');
            if (!el) {
              el = document.createElement('textarea');
              el.id = '__pw_clipboard_sink';
              el.autocomplete = 'off';
              el.style.position = 'fixed';
              el.style.opacity = '0';
              el.style.pointerEvents = 'none';
              el.style.left = '-9999px';
              el.style.top = '0';
              document.body.appendChild(el);
            }
            el.value = '';
            el.focus();
          }
        """)
        # 전면창 전제
        try: await page.bring_to_front()
        except Exception: pass
        await page.keyboard.down("Control")
        await page.keyboard.press("V")
        await page.keyboard.up("Control")
        await page.wait_for_timeout(80)
        val = await page.locator("#__pw_clipboard_sink").input_value()
        return (val or "").strip()
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

def _extract_url_fuzzy(text: str) -> str:
    cleaned = re.sub(r"[\u200b\u200c\u200d\u2060]", "", text or "")
    cleaned = cleaned.replace("\xa0", " ")
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

async def _click_copy_and_get_clipboard_text(
    page: Page,
    btn: Locator,
    *,
    retries: int = 15,
    wait_ms: int = 160
) -> str:
    # 전면 포커스
    try: await page.bring_to_front()
    except Exception: pass

    # baseline(모든 프레임)
    prev_seq = await _get_copy_seq_any(page)
    try:
        prev_os = await asyncio.to_thread(_read_os_clipboard_windows)
    except Exception:
        prev_os = ""

    # 클릭
    try:
        await btn.scroll_into_view_if_needed()
        await expect(btn).to_be_visible(timeout=T_SHORT)
        try:
            await btn.click()
        except Exception:
            await btn.click(force=True)
    except Exception:
        try:
            await btn.evaluate("(el) => el.click()")
        except Exception:
            pass

    # 프레임 전역 시퀀스 증가 대기
    await _wait_for_new_copy_any(page, prev_seq, timeout_ms=1_500)

    # 재시도 루프
    for i in range(retries):
        # 1) 스니퍼 값(모든 프레임)
        for scope in _all_scopes(page):
            try:
                t = await scope.evaluate(
                    "() => window.__last_copied || (window.__copied_texts && window.__copied_texts.slice(-1)[0]) || ''"
                )
                if t and t.strip():
                    return t.strip()
            except Exception:
                continue

        # 2) navigator.clipboard.readText (권한 부여 전제)
        for scope in _all_scopes(page):
            try:
                nav_t = await scope.evaluate("""async () => {
                    try { return await navigator.clipboard.readText(); } catch (e) { return ''; }
                }""")
                if nav_t and nav_t.strip():
                    return nav_t.strip()
            except Exception:
                continue

        # 3) 붙여넣기 우회
        try:
            val = await _read_clipboard_via_paste(page)
            if val and val.strip() and val != prev_os:
                return val.strip()
        except Exception:
            pass

        # 4) OS 클립보드
        try:
            cur_os = await asyncio.to_thread(_read_os_clipboard_windows)
            if cur_os and cur_os.strip() and cur_os != prev_os:
                return cur_os.strip()
        except Exception:
            pass

        # 5) 화면의 입력칸 폴백
        input_selectors = [
            "input#prop-view-document-internal-url",
            "input[name*='internal'][name*='url']",
            "input[type='text'][id*='internal'][id*='url']",
            "input[type='text'][name*='url']",
        ]
        for scope in _all_scopes(page):
            for sel in input_selectors:
                loc = scope.locator(sel)
                try:
                    if await loc.count():
                        v = await loc.first.input_value()
                        if v and v.strip():
                            return v.strip()
                except Exception:
                    continue

        # 6) 본문에서 URL 추출
        try:
            for scope in _all_scopes(page):
                txt = await scope.evaluate("() => document.body ? document.body.innerText || '' : '' ")
                m = re.search(r'https?://[^\s<>\'\"()\\[\\]]+', txt or '')
                if m:
                    return m.group(0)
        except Exception:
            pass

        await page.wait_for_timeout(wait_ms * (i + 1))

    return ""

# ────────────────────────────────────────────────────────────
# 시나리오 메인
async def run_scenario_async(page: Page, job_dir: pathlib.Path, *, 시험번호: str, 연도: str, 날짜: str, **kwargs) -> str:
    assert 시험번호 and 연도 and 날짜, "필수 인자(시험번호/연도/날짜)가 비었습니다."
    job_dir.mkdir(parents=True, exist_ok=True)

    # 좌측 트리 가시성
    left_tree = page.locator(SEL["left_tree"])
    await expect(left_tree).to_be_visible(timeout=T_LONG)

    # 1) 연도 → 2) GS인증심의위원회 → 3) 날짜 → 4) 시험번호
    await _tree_click_by_name_contains(left_tree, 연도, timeout=T_SHORT)
    await _tree_click_by_name_contains(left_tree, "GS인증심의위원회", timeout=T_SHORT)
    await _tree_click_by_name_contains(left_tree, 날짜, timeout=T_SHORT)
    await _tree_click_by_name_contains(left_tree, 시험번호, timeout=T_SHORT)

    # ★ 문서 스팬이 실제로 붙는 시점까지 대기 (networkidle 대신)
    await page.wait_for_selector(SEL["doc_span"], state="attached", timeout=T_MED)

    # 4.5) 문서명 스팬 클릭(우선순위: '시험성적서' 경계일치 → 시험번호)
    clicked = await _try_click_doc_name_span(page, 시험번호, timeout=T_MED)
    if clicked:
        # pane-2가 열리는 UI라면 내부 시그널(파일 tbody attach)로 확인
        try:
            await page.wait_for_selector(SEL["file_tbody"], state="attached", timeout=T_MED)
        except Exception:
            pass

    # 5) 파일리스트 스코프 결정
    try:
        scope = await _find_filelist_scope(page, timeout=T_MED)
    except Exception:
        # 한 번 더 DOM 안정화
        await page.wait_for_timeout(200)
        scope = await _find_filelist_scope(page, timeout=T_MED)

    # 6) 대상 행 찾기
    row = await _find_target_row(scope, 시험번호)
    if not row:
        await _dump_rows_for_debug(scope, job_dir)
        raise RuntimeError(f'파일 목록에서 "{시험번호}" & "시험성적서"를 포함하는 행을 못 찾았습니다.')

    # 7) 체크박스 체크
    await row.scroll_into_view_if_needed()
    await expect(row).to_be_visible(timeout=T_MED)
    checkbox = row.locator('input[type="checkbox"]')
    if await checkbox.count() == 0:
        checkbox = row.locator('td.prop-view-file-list-item-checkbox input[type="checkbox"], input.file-list-type')
    await expect(checkbox.first).to_be_visible(timeout=T_SHORT)
    await checkbox.first.check(timeout=T_SHORT)

    # 8) 복사 스니퍼 주입
    await _prime_copy_sniffer(page)

    # 9) 내부 URL 복사 버튼 찾기
    copy_btn = await _find_copy_button(page, timeout=T_MED)

    # 10) 클릭 후, 클립보드 텍스트 직접 읽기(멀티 루트)
    copied_text = await _click_copy_and_get_clipboard_text(page, copy_btn, retries=15, wait_ms=160)
    if not copied_text:
        await page.screenshot(path=str(job_dir / "url_extract_fail.png"), full_page=False)
        raise RuntimeError("복사는 되었지만 텍스트를 읽지 못했습니다.")

    # 11) URL 추출
    url = _extract_url_fuzzy(copied_text) or copied_text.strip()
    await page.evaluate("(u) => console.log('EXTRACTED_URL:', u)", url)

    # 산출물
    await page.screenshot(path=str(job_dir / "list_done.png"), full_page=False)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")
    return url
