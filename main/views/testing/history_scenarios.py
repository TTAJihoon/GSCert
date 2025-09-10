import os, pathlib, re
from playwright.sync_api import Page, expect, TimeoutError as PWTimeout

BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
LOGIN_ID    = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW    = os.getenv("LOGIN_PW", "12sqec34!")

def _wait_login_completed(page, timeout=30000):
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

def run_scenario_sync(page: Page, job_dir: pathlib.Path, *, 시험번호: str, hold_seconds: int = 0, **kwargs) -> str:
    assert 시험번호, "시험번호가 비어 있습니다."

    # 0) 홈 진입
    page.goto(f"{BASE_ORIGIN}/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # 1) 로그인 필요 시 처리(명시 클릭 + 내비 대기)
    if "login" in page.url.lower() or page.locator("#form-login").count() > 0:
        user = page.locator("input[name='user_id']")
        pwd  = page.locator("input[name='password']")
        expect(user).to_be_visible(timeout=15000)
        expect(pwd).to_be_visible(timeout=15000)
        user.fill(LOGIN_ID)
        pwd.fill(LOGIN_PW)

        login_btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
        expect(login_btn).to_be_visible(timeout=10000)
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                login_btn.click()
        except PWTimeout:
            login_btn.click()
            page.wait_for_load_state("networkidle")
        _wait_login_completed(page, timeout=30000)

    # (옵션) 로그인 완료 직후 잠깐 유지하고 싶을 때
    if hold_seconds:
        page.screenshot(path=str(job_dir / "after_login.png"), full_page=True)
        page.wait_for_timeout(hold_seconds * 1000)

    # 2) 검색
    search_input = page.locator("input.top-search2-input[name='q']")
    expect(search_input).to_be_visible(timeout=60000)

    search_value = f"{시험번호} 시험성적서"
    search_input.fill(search_value)
    search_btn = page.locator("div.top-search2-btn.hcursor")
    expect(search_btn).to_be_visible(timeout=10000)
    search_btn.click()
    page.wait_for_load_state("networkidle")

    # 3) 결과 필터링 후 새창 열기
    title_cards = page.locator("div.search_ftr_file_list_title.hcursor.ellipsis")
    expect(title_cards).to_be_visible(timeout=30000)

    count = title_cards.count()
    target_index = None
    sv_lower = search_value.lower()
    for i in range(count):
        txt = title_cards.nth(i).inner_text().strip()
        if (sv_lower in txt.lower()) and ("docx" in txt.lower()):
            target_index = i
            break
    if target_index is None:
        raise RuntimeError("검색 결과에서 (검색값 & 'docx') 조건에 맞는 항목을 찾지 못했습니다.")

    container = title_cards.nth(target_index).locator(
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

    # 4) 내부 URL 복사 시도 (권한 불가 시 폴백)
    copy_btn = popup.locator("div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor")
    expect(copy_btn).to_be_visible(timeout=15000)
    copy_btn.click()

    copied_text = ""
    try:
        # 클립보드 권한이 허용된 경우
        copied_text = popup.evaluate("navigator.clipboard.readText()")
    except Exception:
        # 폴백: 입력 필드가 있으면 그 값 읽기
        try:
            copied_text = popup.locator("input#prop-view-document-internal-url").input_value()
        except Exception:
            copied_text = ""

    # 아티팩트 저장
    popup.screenshot(path=str(job_dir / "popup_done.png"), full_page=True)
    page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

    if not copied_text:
        raise RuntimeError("복사된 문장을 읽지 못했습니다. 권한/정책/요소 변동을 확인하세요.")

    return copied_text
