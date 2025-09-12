import os
import re
import pathlib
import traceback
import asyncio
import time
from typing import Optional

from asgiref.sync import sync_to_async
from django.utils import timezone
from playwright.async_api import async_playwright, Browser

from ...models import Job
from .history_scenarios import run_scenario_async  # 그대로 사용 (async 시나리오)  # ← 그대로 유지

# ────────────────────────────────────────────────────────────
# 경로/환경
RUNS_DIR = pathlib.Path(__file__).resolve().parent.parent / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

AUTH_DIR = pathlib.Path(__file__).resolve().parent.parent / "auth_states"
AUTH_DIR.mkdir(parents=True, exist_ok=True)
USER_KEY = os.getenv("PW_STATE_USER", "shared")
AUTH_STATE_PATH = AUTH_DIR / f"{USER_KEY}.json"

PW_CHANNEL  = os.getenv("PW_CHANNEL", "chrome")
PW_HEADLESS = (os.getenv("PW_HEADLESS", "true").lower() == "true")  # ← 기본값을 headless=True로
PW_TZ       = os.getenv("PW_TZ", "Asia/Seoul")
UA_CHROME   = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# 브라우저 재사용 한도(안정성): 시간/작업수 기준으로 주기적 재기동
BROWSER_MAX_AGE_SEC = int(os.getenv("BROWSER_MAX_AGE_SEC", "1800"))  # 30분
BROWSER_MAX_JOBS    = int(os.getenv("BROWSER_MAX_JOBS", "200"))
PW_LAUNCH_ARGS      = os.getenv("PW_LAUNCH_ARGS", "--disable-dev-shm-usage --no-sandbox").split()

# ────────────────────────────────────────────────────────────
# DB helpers

@sync_to_async
def _mark(job_id: str, status: str, **extra):
    extra.setdefault("updated_at", timezone.now())
    return Job.objects.filter(pk=job_id).update(status=status, **extra)

# ────────────────────────────────────────────────────────────
# 입력 파싱

def _parse_fields_from_data(data: dict):
    test_no = data.get("시험번호") or data.get("test_no") or data.get("cert_no") or ""
    raw_date = data.get("인증일자") or data.get("cert_date") or data.get("인증일") or ""
    digits = re.sub(r"\D", "", raw_date or "")
    date8 = digits[:8] if len(digits) >= 8 else ""
    year4 = date8[:4] if len(date8) == 8 else ""
    if not test_no or not date8 or not year4:
        raise ValueError(f"필수 값 누락: 시험번호={test_no!r}, 인증일자(raw)={raw_date!r} → (연도={year4!r}, 날짜={date8!r})")
    return test_no, year4, date8

# ────────────────────────────────────────────────────────────
# 로그인 상태 유틸 (이전 코드 재사용)

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

async def _bootstrap_state(pw):
    # 최초/만료 시 세션 부트스트랩 (headful 필요 없음 → headless로도 가능)
    browser = await pw.chromium.launch(channel=PW_CHANNEL, headless=True, args=PW_LAUNCH_ARGS)
    context = await browser.new_context(user_agent=UA_CHROME, timezone_id=PW_TZ, locale="ko-KR")
    page = await context.new_page()

    BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
    LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")

    await page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    if not await _is_logged_in(page):
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        login_id = os.getenv("LOGIN_ID", "")
        login_pw = os.getenv("LOGIN_PW", "")
        if login_id and login_pw:
            from playwright.async_api import expect, TimeoutError as PWTimeout
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

    if not await _is_logged_in(page):
        await context.close(); await browser.close()
        raise RuntimeError("세션 부트스트랩 실패")

    await context.storage_state(path=str(AUTH_STATE_PATH))
    await context.close(); await browser.close()

async def _check_state_valid(pw) -> bool:
    BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
    if not AUTH_STATE_PATH.exists():
        return False
    browser = await pw.chromium.launch(channel=PW_CHANNEL, headless=True, args=PW_LAUNCH_ARGS)
    context = await browser.new_context(
        storage_state=str(AUTH_STATE_PATH),
        user_agent=UA_CHROME, timezone_id=PW_TZ, locale="ko-KR",
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
# 브라우저 재사용 풀 (워커 프로세스당 1개 유지, TTL/작업수 초과 시 재시작)

_pl = None
_browser: Optional[Browser] = None
_launched_at: float = 0.0
_jobs_done: int = 0

async def _get_pw():
    global _pl
    if _pl is None:
        _pl = await async_playwright().start()
    return _pl

async def _launch_browser() -> Browser:
    global _browser, _launched_at, _jobs_done
    pw = await _get_pw()
    _browser = await pw.chromium.launch(channel=PW_CHANNEL, headless=PW_HEADLESS, args=PW_LAUNCH_ARGS)
    _launched_at = time.monotonic()
    _jobs_done = 0
    return _browser

async def _get_browser() -> Browser:
    global _browser, _launched_at, _jobs_done
    need_new = (
        _browser is None
        or not _browser.is_connected()
        or (BROWSER_MAX_AGE_SEC and (time.monotonic() - _launched_at) > BROWSER_MAX_AGE_SEC)
        or (BROWSER_MAX_JOBS and _jobs_done >= BROWSER_MAX_JOBS)
    )
    if need_new:
        try:
            if _browser:
                await _browser.close()
        except Exception:
            pass
        await _launch_browser()
    return _browser  # type: ignore

# ────────────────────────────────────────────────────────────
# 메인 로직 (async)  +  RQ용 동기 래퍼

async def _run_playwright_job_task_async(job_id: str, data: dict):
    from playwright.async_api import expect  # 필요시
    await _mark(job_id, "RUNNING")

    job_dir = RUNS_DIR / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    page = None
    try:
        test_no, year4, date8 = _parse_fields_from_data(data)

        # 2) 재사용 브라우저에서 context/page만 새로
        browser = await _get_browser()
        ctx_kwargs = dict(
            accept_downloads=True,
            timezone_id=PW_TZ,
            locale="ko-KR",
            user_agent=UA_CHROME,
        )
        if AUTH_STATE_PATH.exists():
            ctx_kwargs["storage_state"] = str(AUTH_STATE_PATH)

        context = await browser.new_context(**ctx_kwargs)

        # (선호) 클립보드 권한
        try:
            await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_ORIGIN)
        except Exception:
            pass

        page = await context.new_page()

        # ★ 지연 로그인: 로그인 페이지면 그 자리에서 로그인하고 state를 '새로' 저장
        await page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        if "/auth/login" in page.url.lower() or await page.locator("#form-login").count() > 0:
            from playwright.async_api import expect, TimeoutError as PWTimeout
            login_url = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")
            await page.goto(login_url, wait_until="domcontentloaded")

            user = page.locator("input[name='user_id']")
            pwd  = page.locator("input[name='password']")
            await expect(user).to_be_visible(timeout=10000)
            await expect(pwd).to_be_visible(timeout=10000)
            await user.fill(os.getenv("LOGIN_ID", ""))
            await pwd.fill(os.getenv("LOGIN_PW", ""))

            btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
            await expect(btn).to_be_visible(timeout=10000)
            try:
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                    await btn.click()
            except PWTimeout:
                await btn.click(); await page.wait_for_load_state("networkidle")

            # ★ 워커 전용(shard_X.json)으로 저장 → 다음부터는 storage_state로 바로 로그인 유지
            try:
                await context.storage_state(path=str(AUTH_STATE_PATH))
            except Exception:
                pass

        # 3) 시나리오 실행
        final_link = await run_scenario_async(
            page, job_dir,
            시험번호=test_no, 연도=year4, 날짜=date8
        )

        (job_dir / "copied.txt").write_text(final_link or "", encoding="utf-8")

        await context.close()
        # 브라우저는 닫지 않음(재사용)

        # 작업 카운트 증가
        global _jobs_done
        _jobs_done += 1

        await _mark(job_id, "DONE", final_link=final_link)

    except Exception as e:
        try:
            if page:
                await page.screenshot(path=str(job_dir / "error.png"), full_page=True)
        except Exception:
            pass
        await _mark(job_id, "ERROR", error=f"{e}\n{traceback.format_exc()}")

def run_playwright_job_task_sync(job_id: str, data: dict):
    """
    RQ enqueue 대상: 동기 함수.
    내부에서 asyncio.run으로 async 작업을 실행.
    """
    return asyncio.run(_run_playwright_job_task_async(job_id, data))
