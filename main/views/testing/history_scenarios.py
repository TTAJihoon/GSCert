# -*- coding: utf-8 -*-
"""
- 전달받은 Page/Context만 사용 (절대 async_playwright()를 여기서 생성하지 않음)
- 흐름: 홈 진입 → 필요 시 로그인 처리 → 검색 → (요청사항) 타이틀 div(". {시험번호}") → 폴더로 이동 →
        파일 목록에서 tr(시험번호+시험성적서) 체크 → 내부 URL 복사 → 산출물 저장
"""

import os
import re
import pathlib
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

    # ─────────────────────────────────────────────────────────────
    # (요청하신 수정 구간) 조회된 화면에서 수행할 4단계

    # 1) ". {시험번호}" 텍스트를 가진 리스트 타이틀 div 선택 (예: ". GS-A-25-0099")
    target_text_regex = re.compile(rf"\.\s*{re.escape(시험번호)}")
    title_div = page.locator(
        "div.search_ftr_file_list_title.hcursor.ellipsis"
    ).filter(has_text=target_text_regex).first
    await expect(title_div).to_be_visible(timeout=30000)
    print("[DEBUG] 타겟 타이틀 div 발견")

    # 2) 상위 컨테이너 .search_ftr_file_cont → '폴더로 이동' 버튼 클릭
    container = title_div.locator("xpath=ancestor::div[contains(@class,'search_ftr_file_cont')]")
    move_btn = container.locator(
        "span.btn-folder-move.hcursor[events='folder-fullpath-click'][title='폴더로 이동']"
    )
    await expect(move_btn).to_be_visible(timeout=20000)
    await move_btn.click()
    await page.wait_for_load_state("networkidle")

    # 3) #prop-view-file-list-tbody에서
    #    title에 {시험번호}와 '시험성적서'가 모두 포함된 tr을 찾아 체크박스 클릭
    tbody = page.locator("#prop-view-file-list-tbody")
    await expect(tbody).to_be_visible(timeout=30000)

    tr_sel = f'tr[title*="{시험번호}"][title*="시험성적서"]'
    target_row = tbody.locator(tr_sel).first
    await expect(target_row).to_be_visible(timeout=20000)

    checkbox = target_row.locator('td.prop-view-file-list-item-checkbox input.file-list-type')
    await checkbox.check(timeout=10000)  # 체크 상태 강제 보장
    print("[DEBUG] 파일 목록 체크박스 체크 완료")

    # 4) 내부 URL 복사 버튼 클릭 → 텍스트 획득
    copy_btn = page.locator(
        "div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor"
    )
    await expect(copy_btn).to_be_visible(timeout=20000)
    await copy_btn.click()

    copied_text = ""
    try:
        copied_text = await page.evaluate("navigator.clipboard.readText()")
    except Exception:
        try:
            copied_text = await page.locator("input#prop-view-document-internal-url").input_value()
        except Exception:
            copied_text = ""

    # 5) 산출물 저장 및 반환
    await page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    if not copied_text:
        raise RuntimeError("복사된 문장을 읽지 못했습니다. 권한/정책/요소 변동을 확인하세요.")

    print(f"[DEBUG] 복사된 문장: {copied_text!r}")
    return copied_text
