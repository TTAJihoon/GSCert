# tasks/playwright_pool.py
import os, time, asyncio, atexit
from typing import Callable, Awaitable, Any
from playwright.async_api import async_playwright, Browser, Page

# -------------------------
# 설정 (환경변수로 오버라이드 가능)
# -------------------------
PW_BROWSER          = os.getenv("PW_BROWSER", "chromium")  # chromium|firefox|webkit
PW_HEADLESS         = os.getenv("PW_HEADLESS", "1") == "1" # 운영: 1(=True)
PW_LAUNCH_ARGS      = os.getenv("PW_LAUNCH_ARGS", "--disable-dev-shm-usage --no-sandbox").split()
BROWSER_MAX_AGE_SEC = int(os.getenv("BROWSER_MAX_AGE_SEC", "1800"))  # 브라우저 최대 수명(초)
BROWSER_MAX_JOBS    = int(os.getenv("BROWSER_MAX_JOBS", "200"))      # 브라우저 당 처리 최대 작업 수
PW_STORAGE_STATE    = os.getenv("PW_STORAGE_STATE", "")              # ex) "state.json" (로그인 세션 재사용시)

# -------------------------
# 싱글톤 (워커 프로세스당)
# -------------------------
_pl = None
_browser: Browser | None = None
_launched_at: float = 0.0
_jobs_done: int = 0

async def _launch_browser() -> Browser:
    global _pl, _browser, _launched_at, _jobs_done
    if _pl is None:
        _pl = await async_playwright().start()
    # 선택한 브라우저 타입
    btype = getattr(_pl, PW_BROWSER)
    _browser = await btype.launch(headless=PW_HEADLESS, args=PW_LAUNCH_ARGS)
    _launched_at = time.monotonic()
    _jobs_done = 0
    return _browser

async def get_browser() -> Browser:
    """ TTL/작업수 초과 시 재기동하며, 연결 끊김에도 복구 """
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

async def run_with_page(job: Callable[[Page], Awaitable[Any]]) -> Any:
    """작업마다 새 context/page만 생성하고, 작업 후 context만 닫는다."""
    global _jobs_done
    browser = await get_browser()
    context = await browser.new_context(storage_state=(PW_STORAGE_STATE or None))
    page = await context.new_page()
    try:
        return await job(page)
    finally:
        try:
            await context.close()
        finally:
            _jobs_done += 1

# 프로세스 종료 시 브라우저 정리
def _cleanup():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def _close_all():
            global _browser, _pl
            try:
                if _browser:
                    await _browser.close()
            except Exception:
                pass
            try:
                if _pl:
                    await _pl.stop()
            except Exception:
                pass
        loop.run_until_complete(_close_all())
        loop.close()
    except Exception:
        pass

atexit.register(_cleanup)
