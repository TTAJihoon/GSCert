# -*- coding: utf-8 -*-
"""
- 여기서는 전달받은 Page/Context만 사용 (절대 sync_playwright()를 열지 않음)
- 흐름: 홈 진입 → 필요 시 로그인 처리 → 검색 → 결과 새창 → 내부 URL 복사 → 산출물 저장
"""
import os, re
import pathlib
from playwright.sync_api import Page, expect, TimeoutError as PWTimeout

BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
LOGIN_ID    = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW    = os.getenv("LOGIN_PW", "12sqec34!")

def _wait_login_completed(page: Page, timeout=30000):
    page.wait_for_function(
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

def run_scenario_sync(page: Page, job_dir: pathlib.Path, *, 시험번호: str, **kwargs) -> str:
    assert 시험번호, "시험번호가 비어 있습니다."
    job_dir.mkdir(parents=True, exist_ok=True)

    # 0) 홈 진입
    page.goto(f"{BASE_ORIGIN}/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # 1) 로그인 필요 시 처리
    if "login" in page.url.lower() or page.locator("#form-login").count() > 0:
        user = page.locator("input[name='user_id']")
        pwd  = page.locator("input[name='password']")
        expect(user).to_be_visible(timeout=15000)
        expect(pwd).to_be_visible(timeout=15000)
        user.fill(LOGIN_ID); pwd.fill(LOGIN_PW)

        btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
        expect(btn).to_be_visible(timeout=10000)
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                btn.click()
        except PWTimeout:
            btn.click(); page.wait_for_load_state("networkidle")
        _wait_login_completed(page, timeout=30000)

    # 2) 검색
    search_input = page.locator("input.top-search2-input[name='q']")
    expect(search_input).to_be_visible(timeout=60000)

    search_value = f"{시험번호} 시험성적서"
    print(f"[DEBUG] 검색값 = {search_value}")
    search_input.fill(search_value)

    search_btn = page.locator("div.top-search2-btn.hcursor")
    expect(search_btn).to_be_visible(timeout=10000)
    search_btn.click()
    page.wait_for_load_state("networkidle")

    # 3) 결과 필터링 후 새창 열기
    title_cards = page.locator("div.search_ftr_file_list_title.hcursor.ellipsis")
    # ✅ 최소 1개가 보일 때까지(첫 번째) 기다린 뒤, 텍스트로 좁힘
    title_cards.first.wait_for(state="visible", timeout=30000)

    # 3-1) 우선: 시험번호 + 'docx' 포함으로 좁히기
    cand = title_cards.filter(has_text=re.compile(re.escape(시험번호), re.I)) \
                      .filter(has_text=re.compile(r"\bdocx\b", re.I))

    # 3-2) 없으면 시험번호만
    if cand.count() == 0:
        cand = title_cards.filter(has_text=re.compile(re.escape(시험번호), re.I))

    # 3-3) 그래도 없으면 전체에서 루프 탐색(기존 로직)
    target_el = None
    if cand.count() > 0:
        target_el = cand.first
    else:
        count = title_cards.count()
        print(f"[DEBUG] 결과 항목 수: {count}")
        sv_lower = f"{시험번호}".lower()
        for i in range(count):
            txt = title_cards.nth(i).inner_text().strip()
            low = txt.lower()
            print(f"[DEBUG] [{i}] {txt}")
            if (sv_lower in low) and ("docx" in low):
                target_el = title_cards.nth(i)
                break
        if target_el is None and count > 0:
            # 최후 수단: 첫 항목
            target_el = title_cards.first

    # 상위 컨테이너 → 새창 버튼 클릭
    container = target_el.locator(
        "xpath=ancestor::div[contains(@class,'search_ftr_file_cont')]"
    )
    newwin_btn = container.locator(
        "span.search_ftr_path_newwindow.hcursor[events='edm-document-property-view-newWindow-click']"
    )

    with page.expect_popup() as popup_info:
        newwin_btn.click()
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded")
    popup.wait_for_load_state("networkidle")

    # 4) 내부 URL 복사 (권한 실패 대비 폴백 포함)
    copy_btn = popup.locator("div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor")
    expect(copy_btn).to_be_visible(timeout=15000)
    copy_btn.click()

    copied_text = ""
    try:
        copied_text = popup.evaluate("navigator.clipboard.readText()")
    except Exception:
        try:
            copied_text = popup.locator("input#prop-view-document-internal-url").input_value()
        except Exception:
            copied_text = ""

    # 5) 산출물 저장
    popup.screenshot(path=str(job_dir / "popup_done.png"), full_page=True)
    page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    if not copied_text:
        raise RuntimeError("복사된 문장을 읽지 못했습니다. 권한/정책/요소 변동을 확인하세요.")

    return copied_text
