# playwright_login_wait_then_exit.py
from playwright.sync_api import Page, sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
import os, pathlib
import time

LOGIN_URL = "http://210.104.181.10/auth/login/loginView.do"
LOGIN_ID  = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW  = os.getenv("LOGIN_PW", "12sqec34!")  # 필요 시 환경변수로 덮어쓰기

def run_scenario_sync(page: Page, job_dir: pathlib.Path, *, 시험번호: str, **kwargs) -> str:
    with sync_playwright() as p:
        # 디버깅 시 headless=False 권장
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        context.set_default_timeout(15000)
        page = context.new_page()

        # 1) 로그인 페이지 진입
        page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # 2) ID/PW 입력
        user = page.locator("input[name='user_id']")
        pwd  = page.locator("input[name='password']")
        expect(user).to_be_visible()
        expect(pwd).to_be_visible()
        user.fill(LOGIN_ID)
        pwd.fill(LOGIN_PW)

        # 3) 로그인 버튼 클릭 (네비게이션/비네비게이션 모두 대비)
        login_btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
        expect(login_btn).to_be_visible()

        try:
            # 클릭으로 실제 네비가 일어나면 여기에서 기다림
            with page.expect_navigation(wait_until="networkidle", timeout=5000):
                login_btn.click()
        except PlaywrightTimeoutError:
            # AJAX 로그인 등 네비가 없을 수도 있음 → 클릭 후 네트워크 안정까지 대기
            login_btn.click()
            page.wait_for_load_state("networkidle")

        # 4) 로그인 완료 판정 (URL/폼/바디 ID 변화 중 하나라도 만족)
        page.wait_for_function(
            """
            () => {
              const notLoginURL = !/\\/auth\\/login/i.test(location.href);
              const form = document.querySelector('#form-login');
              const formGoneOrHidden = !form || form.offsetParent === null || getComputedStyle(form).display === 'none';
              const bodyChanged = document.body && document.body.id !== 'login';
              return notLoginURL || formGoneOrHidden || bodyChanged;
            }
            """,
            timeout=30000
        )

        print("[INFO] 로그인 완료로 판단됨. 10초 대기 후 종료합니다…")
        time.sleep(10)

        context.close()
        browser.close()

    return "ok"
