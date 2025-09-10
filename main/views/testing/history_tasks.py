# -*- coding: utf-8 -*-
"""
- Playwright Async API 사용
- storage_state(auth_states/<USER_KEY>.json)로 세션 재사용
- 업스트림(JS)이 보내준 body json에서 '시험번호'와 '인증일자'(예: 2025.08.25)를 받아
  - 연도 = 2025
  - 날짜 = 20250825
  - 시험번호 = 원문 그대로
  를 계산해 history_scenarios.run_scenario_async에 넘긴다.
"""

import os
import re
import pathlib
import traceback
from asgiref.sync import sync_to_async
from django.utils import timezone
from playwright.async_api import async_playwright, expect, TimeoutError as PWTimeout

from ...models import Job
from .history_scenarios import run_scenario_async  # ← 시나리오도 async

# ────────────────────────────────────────────────────────────
# 경로/환경
RUNS_DIR = pathlib.Path(__file__).resolve().parent.parent / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

AUTH_DIR = pathlib.Path(__file__).resolve().parent.parent / "auth_states"
AUTH_DIR.mkdir(parents=True, exist_ok=True)
USER_KEY = os.getenv("PW_STATE_USER", "shared")
AUTH_STATE_PATH = AUTH_DIR / f"{USER_KEY}.json"

PW_CHANNEL  = os.getenv("PW_CHANNEL", "chrome")
PW_HEADLESS = os.getenv("PW_HEADLESS", "false").lower() == "true"
TIMEZONE_ID = os.getenv("PW_TZ", "Asia/Seoul")
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")

UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# ────────────────────────────────────────────────────────────
# DB helpers (async-safe)

@sync_to_async
def _mark(job_id: str, status: str, **extra):
    extra.setdefault("updated_at", timezone.now())
    return Job.objects.filter(pk=job_id).update(status=status, **extra)

# ────────────────────────────────────────────────────────────
# 로그인 상태 판정/대기 (공통: async)

async def _is_logged_in(page) -> bool:
    if "/auth/login" in page.url.lower():
        return False
    try:
        return await page.locator("#form-login").count() == 0
    except Exception:
        return True

async def _wait_login_completed(page, timeout=30000):
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

# ────────────────────────────────────────────────────────────
# 세션 상태 부트스트랩/검증 (Async)

async def _bootstrap_state(pw):
    browser = await pw.chromium.launch(
        channel=PW_CHANNEL, headless=False, args=["--start-maximized", "--disable-gpu", "--no-sandbox"]
    )
    context = await browser.new_context(user_agent=UA_CHROME, timezone_id=TIMEZONE_ID, locale="ko-KR")
    page = await context.new_page()

    await page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    if not await _is_logged_in(page):
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        login_id = os.getenv("LOGIN_ID", "")
        login_pw = os.getenv("LOGIN_PW", "")
        if login_id and login_pw:
            try:
                user = page.locator("input[name='user_id']")
                pwd  = page.locator("input[name='password']")
                await expect(user).to_be_visible(timeout=10000)
                await expect(pwd).to_be_visible(timeout=10000)
                await user.fill(login_id); await pwd.fill(login_pw)
                btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
                await expect(btn).to_be_visible(timeout=10000)
                try:
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        await btn.click()
                except PWTimeout:
                    await btn.click(); await page.wait_for_load_state("networkidle")
                await _wait_login_completed(page, timeout=30000)
            except Exception:
                pass

    if not await _is_logged_in(page):
        await context.close(); await browser.close()
        raise RuntimeError("세션 부트스트랩 실패")

    await context.storage_state(path=str(AUTH_STATE_PATH))
    await context.close(); await browser.close()

async def _check_state_valid(pw) -> bool:
    if not AUTH_STATE_PATH.exists():
        return False
    browser = await pw.chromium.launch(channel=PW_CHANNEL, headless=True, args=["--disable-gpu", "--no-sandbox"])
    context = await browser.new_context(
        storage_state=str(AUTH_STATE_PATH),
        user_agent=UA_CHROME, timezone_id=TIMEZONE_ID, locale="ko-KR",
    )
    page = await context.new_page()
    await page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    ok = await _is_logged_in(page)
    await context.close(); await browser.close()
    return ok

async def _ensure_valid_state(pw):
    if not await _check_state_valid(pw):
        await _bootstrap_state(pw)

# ────────────────────────────────────────────────────────────
# 입력 파싱(helper)

def _parse_fields_from_data(data: dict):
    """
    data: 업스트림(JS)에서 보낸 body json
      - 시험번호: "시험번호" | "test_no" | "cert_no" 등
      - 인증일자: "인증일자" | "cert_date" | "인증일"
        예) "2025.08.25" 또는 "2025-08-25" → 연도=2025, 날짜=20250825
    """
    test_no = data.get("시험번호") or data.get("test_no") or data.get("cert_no") or ""
    raw_date = data.get("인증일자") or data.get("cert_date") or data.get("인증일") or ""
    digits = re.sub(r"\D", "", raw_date or "")
    date8 = digits[:8] if len(digits) >= 8 else ""
    year4 = date8[:4] if len(date8) == 8 else ""
    if not test_no or not date8 or not year4:
        raise ValueError(f"필수 값 누락: 시험번호={test_no!r}, 인증일자(raw)={raw_date!r} → (연도={year4!r}, 날짜={date8!r})")
    return test_no, year4, date8

# ────────────────────────────────────────────────────────────
# 메인 태스크 (Async)

async def run_playwright_job_task(job_id: str, data: dict):
    await _mark(job_id, "RUNNING")

    job_dir = RUNS_DIR / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    page = None
    try:
        test_no, year4, date8 = _parse_fields_from_data(data)

        async with async_playwright() as pw:
            # 1) 세션 상태 확보
            await _ensure_valid_state(pw)

            # 2) 실제 잡 실행 (세션 주입)
            browser = await pw.chromium.launch(
                channel=PW_CHANNEL,
                headless=PW_HEADLESS,
                args=["--disable-gpu", "--no-sandbox",
                      "--disable-features=IsolateOrigins,site-per-process"],
            )
            context = await browser.new_context(
                storage_state=str(AUTH_STATE_PATH),
                accept_downloads=True,
                timezone_id=TIMEZONE_ID,
                locale="ko-KR",
                user_agent=UA_CHROME,
            )

            page = await context.new_page()

            copied_text = await run_scenario_async(
                page, job_dir,
                시험번호=test_no,
                연도=year4,
                날짜=date8
            )

            (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

            await context.close()
            await browser.close()

        await _mark(job_id, "DONE", final_link=copied_text)

    except Exception as e:
        try:
            if page:
                await page.screenshot(path=str(job_dir / "error.png"), full_page=True)
        except Exception:
            pass
        await _mark(job_id, "ERROR", error=f"{e}\n{traceback.format_exc()}")
