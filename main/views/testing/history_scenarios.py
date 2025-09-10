# -*- coding: utf-8 -*-
import os, re, pathlib
from playwright.async_api import Page, expect, TimeoutError as PWTimeout, Error as PWError

BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
LOGIN_ID    = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW    = os.getenv("LOGIN_PW", "12sqec34!")

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

# 새 헬퍼: 페이지/프레임 어디에 있든 문서명 span을 찾아 클릭
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

    # 8) 내부 URL 복사
    copy_btn = scope.locator(
        "div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor"
    )
    await expect(copy_btn).to_be_visible(timeout=20000)

    # 9) alert 처리
    copied_text = ""
    try:
        async with page.expect_event("dialog", timeout=3000) as dlg_info:
            await copy_btn.click()
        dlg = await dlg_info.value
        await dlg.accept()
    except PWTimeout:
        await copy_btn.click()
        ok_btn = page.locator("button:has-text('확인'), .ui-dialog-buttonset button:has-text('확인')")
        if await ok_btn.count():
            await ok_btn.first.click()

    # 클립보드/폴백
    try:
        copied_text = await scope.evaluate("navigator.clipboard.readText()")
    except PWError:
        try:
            copied_text = await scope.locator("input#prop-view-document-internal-url").input_value()
        except Exception:
            copied_text = ""

    if not copied_text:
        # 디버깅에 도움되도록 현재 페이지 스샷 남김
        await page.screenshot(path=str(job_dir / "list_after_copy_fail.png"), full_page=True)
        raise RuntimeError("복사 텍스트를 읽지 못했습니다.")

    # 10) 3번째 줄 URL을 콘솔에 출력
    lines = [ln.strip() for ln in copied_text.splitlines()]
    url_line = lines[2] if len(lines) >= 3 else ""
    if not url_line.startswith("http"):
        m = re.search(r"https?://[^\s]+", copied_text)
        url_line = m.group(0) if m else ""
    await page.evaluate("(u) => console.log('EXTRACTED_URL:', u)", url_line)

    # 산출물
    await page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    return copied_text
