# -*- coding: utf-8 -*-
"""
새 시나리오(트리 탐색 버전)
1) http://210.104.181.10 접속 → 필요시 로그인
2) 좌측 트리 패널(submenu_type="Folder") 찾기
3) name에 {연도} 포함된 a 클릭
4) 하단 트리에서 name에 "GS인증심의위원회" 포함된 a 클릭
5) 하단 트리에서 name에 {날짜} 포함된 a 클릭
6) 하단 트리에서 name에 {시험번호} 포함된 a 클릭
7) 전체 DOM에서 filename에 {시험번호}(=인증번호로 간주)와 "시험성적서" 동시 포함 tr → 체크박스 클릭
8) 내부 URL 복사 버튼 클릭
9) alert(확인) 닫기 (브라우저 네이티브 dialog 또는 in-page 모달 모두 처리)
10) 복사된 텍스트의 3번째 줄(http로 시작)을 찾아 console 탭에 출력(console.log)
"""

import os
import re
import pathlib
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
    """BASE_ORIGIN 접속 → 필요시 로그인 처리"""
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
    """
    좌측 트리(scope=LEFT_TREE 컨테이너)에서 a[name*='text']를 찾아 클릭.
    트리 로딩이 느리면 약간의 폴백 대기 포함.
    """
    link = scope.locator(f"a[name*='{text}']").first
    await expect(link).to_be_visible(timeout=timeout)
    await link.click()

async def run_scenario_async(page: Page, job_dir: pathlib.Path, *, 시험번호: str, 연도: str, 날짜: str, **kwargs) -> str:
    assert 시험번호 and 연도 and 날짜, "필수 인자(시험번호/연도/날짜)가 비었습니다."
    job_dir.mkdir(parents=True, exist_ok=True)

    # 1) 접속/로그인 보장
    await _ensure_logged_in(page)

    # 2) 좌측 트리 패널 등장 대기
    left_tree = page.locator(LEFT_TREE_SEL)
    await expect(left_tree).to_be_visible(timeout=30000)

    # 3) 연도 포함 a 클릭 (예: name="2025 시험서비스")
    await _tree_click_by_name_contains(left_tree, 연도, timeout=20000)

    # 4) GS인증심의위원회 클릭
    await _tree_click_by_name_contains(left_tree, "GS인증심의위원회", timeout=20000)

    # 5) 날짜(YYYYMMDD) 클릭
    await _tree_click_by_name_contains(left_tree, 날짜, timeout=20000)

    # 6) 시험번호 클릭
    await _tree_click_by_name_contains(left_tree, 시험번호, timeout=20000)

    # 6-보강) 콘텐츠 패널 로딩 대기
    await page.wait_for_load_state("networkidle")

    # 7) 파일 목록에서 filename에 시험번호(=인증번호 가정) & '시험성적서' 동시 포함 tr 찾기
    #    (전역 검색 → 없으면 텍스트 기반 폴백)
    row = page.locator(
        f'tr[filename*="{시험번호}"][filename*="시험성적서"]'
    ).first
    if await row.count() == 0:
        # 폴백: 어떤 셀이라도 텍스트 동시 포함
        row = page.locator("tr").filter(has_text=시험번호).filter(has_text="시험성적서").first

    if await row.count() == 0:
        raise RuntimeError(f'파일 목록에서 filename 또는 텍스트로 "{시험번호}" & "시험성적서"를 포함하는 행을 못 찾았습니다.')

    await expect(row).to_be_visible(timeout=20000)

    # 체크박스 클릭
    checkbox = row.locator('td.prop-view-file-list-item-checkbox input[type="checkbox"].file-list-type')
    await checkbox.check(timeout=10000)

    # 8) 내부 URL 복사 버튼 클릭
    copy_btn = page.locator(
        "div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor"
    )
    await expect(copy_btn).to_be_visible(timeout=20000)

    copied_text = ""
    # 9) alert 처리 (브라우저 dialog / in-page 모달 모두 시도)
    try:
        async with page.expect_event("dialog", timeout=3000) as dlg_info:
            await copy_btn.click()
        dlg = await dlg_info.value
        await dlg.accept()
    except PWTimeout:
        # 네이티브 dialog가 아니라면 in-page 모달의 '확인' 버튼 시도
        await copy_btn.click()
        ok_btn = page.locator("button:has-text('확인'), .ui-dialog-buttonset button:has-text('확인')")
        if await ok_btn.count():
            await ok_btn.first.click()

    # 클립보드/입력 폴백 읽기
    try:
        copied_text = await page.evaluate("navigator.clipboard.readText()")
    except PWError:
        try:
            copied_text = await page.locator("input#prop-view-document-internal-url").input_value()
        except Exception:
            copied_text = ""

    if not copied_text:
        raise RuntimeError("복사 텍스트를 읽지 못했습니다.")

    # 10) 3번째 줄의 http URL을 콘솔에 출력
    lines = [ln.strip() for ln in copied_text.splitlines()]
    url_line = lines[2] if len(lines) >= 3 else ""
    if not url_line.startswith("http"):
        # 폴백: 전체 텍스트에서 http(s) URL 1개 추출
        m = re.search(r"https?://[^\s]+", copied_text)
        url_line = m.group(0) if m else ""

    await page.evaluate("(u) => console.log('EXTRACTED_URL:', u)", url_line)

    # 산출물 저장
    await page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    return copied_text
