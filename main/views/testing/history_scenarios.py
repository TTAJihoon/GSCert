# -*- coding: utf-8 -*-
import os, re, pathlib, asyncio
from playwright.async_api import Page, expect, TimeoutError as PWTimeout

BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
LOGIN_ID    = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW    = os.getenv("LOGIN_PW", "12sqec34!")

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

async def _find_filelist_scope(page: Page, timeout=30000):
    """#prop-view-file-list-tbody 가 있는 컨텍스트(Page or Frame)를 찾아 반환"""
    # 1) 메인 페이지
    try:
        await page.wait_for_selector("#prop-view-file-list-tbody", timeout=timeout, state="attached")
        return page
    except Exception:
        pass
    # 2) 프레임들
    for fr in page.frames:
        try:
            await fr.wait_for_selector("#prop-view-file-list-tbody", timeout=1000, state="attached")
            return fr
        except Exception:
            continue
    raise TimeoutError("파일 목록 tbody(#prop-view-file-list-tbody)가 나타나지 않았습니다.")

async def run_scenario_async(page: Page, job_dir: pathlib.Path, *, 시험번호: str, **kwargs) -> str:
    assert 시험번호, "시험번호가 비어 있습니다."
    job_dir.mkdir(parents=True, exist_ok=True)

    # 0) 홈 진입
    await page.goto(f"{BASE_ORIGIN}/", wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # 1) 로그인 필요 시 처리
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

    # 2) 검색
    search_input = page.locator("input.top-search2-input[name='q']")
    await expect(search_input).to_be_visible(timeout=60000)

    search_value = f"{시험번호} 시험성적서"
    print(f"[DEBUG] 검색값 = {search_value}")
    await search_input.fill(search_value)

    search_btn = page.locator("div.top-search2-btn.hcursor")
    await expect(search_btn).to_be_visible(timeout=10000)
    await search_btn.click()
    await page.wait_for_load_state("networkidle")

    # ───────────────────────────────
    # A) ". {시험번호}" 텍스트 가진 타이틀 div 찾기
    target_text_regex = re.compile(rf"\.\s*{re.escape(시험번호)}")
    title_div = page.locator(
        "div.search_ftr_file_list_title.hcursor.ellipsis"
    ).filter(has_text=target_text_regex).first
    await expect(title_div).to_be_visible(timeout=30000)

    # B) 상위 컨테이너의 '폴더로 이동' 클릭  → 같은 탭 전환/라우팅 안전 대기
    container = title_div.locator("xpath=ancestor::div[contains(@class,'search_ftr_file_cont')]")
    move_btn = container.locator(
        "span.btn-folder-move.hcursor[events='folder-fullpath-click'][title='폴더로 이동']"
    )
    await expect(move_btn).to_be_visible(timeout=20000)

    # 네비게이션 발생/미발생 모두 커버
    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=5000):
            await move_btn.click()
    except PWTimeout:
        await move_btn.click()
    # 전환 이후 리스트/패널이 뜰 때까지 대기
    try:
        scope = await _find_filelist_scope(page, timeout=20000)
    except Exception:
        # SPA 로딩이 느릴 때 한 번 더 대기
        await page.wait_for_load_state("networkidle")
        scope = await _find_filelist_scope(page, timeout=15000)

    # C) 파일 목록에서 tr 선택(다단계 폴백)
    tbody = scope.locator("#prop-view-file-list-tbody")
    await expect(tbody).to_be_visible(timeout=30000)

    # 1순위: tr[title*="시험번호"][title*="시험성적서"]
    sel1 = f'tr[title*="{시험번호}"][title*="시험성적서"]'
    row = tbody.locator(sel1).first
    if await row.count() == 0:
        # 2순위: tr:has([title*="..."][title*="시험성적서"])
        row = tbody.locator(f'tr:has([title*="{시험번호}"][title*="시험성적서"])').first
    if await row.count() == 0:
        # 3순위: 텍스트 동시 포함 (AND) - 필드 어디에 있든
        row = tbody.locator("tr").filter(has_text=시험번호).filter(has_text="시험성적서").first

    # 최종 존재 확인 (가시성보다 '존재'를 먼저 본 뒤, 보이기까지 대기)
    if await row.count() == 0:
        raise RuntimeError(f'파일 목록에서 "{시험번호}" & "시험성적서" 조건을 만족하는 행을 찾지 못했습니다.')
    await expect(row).to_be_visible(timeout=20000)

    # 체크박스 클릭
    checkbox = row.locator('td.prop-view-file-list-item-checkbox input.file-list-type')
    await checkbox.check(timeout=10000)
    print("[DEBUG] 파일 목록 체크박스 체크 완료")

    # D) 내부 URL 복사 버튼 클릭 → 텍스트 획득
    #   (같은 탭/프레임 내에 있는 버튼을 같은 scope로 찾음)
    copy_btn = scope.locator(
        "div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor"
    )
    await expect(copy_btn).to_be_visible(timeout=20000)
    await copy_btn.click()

    copied_text = ""
    try:
        # 프레임일 수도 있으니 같은 scope에서 읽기
        copied_text = await scope.evaluate("navigator.clipboard.readText()")
    except Exception:
        try:
            copied_text = await scope.locator("input#prop-view-document-internal-url").input_value()
        except Exception:
            copied_text = ""

    # E) 산출물
    await page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    if not copied_text:
        raise RuntimeError("복사된 문장을 읽지 못했습니다. 권한/정책/요소 변동을 확인하세요.")

    print(f"[DEBUG] 복사된 문장: {copied_text!r}")
    return copied_text
