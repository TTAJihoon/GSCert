import os
import asyncio
import logging
from django.apps import AppConfig
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)

POOL_SIZE = 5
BROWSER_POOL: asyncio.Queue[Browser] = asyncio.Queue(maxsize=POOL_SIZE)
_playwright = None  # async_playwright() 핸들 보관

async def _launch_browser() -> Browser:
    global _playwright
    if _playwright is None:
        _playwright = await async_playwright().start()
    # 필요 시 chromium → firefox/webkit 변경
    browser = await _playwright.chromium.launch(headless=True)
    return browser

async def init_browser_pool():
    logger.info("Playwright 브라우저 풀 초기화를 시작합니다...")
    for i in range(POOL_SIZE):
        b = await _launch_browser()
        await BROWSER_POOL.put(b)
        logger.info("브라우저 %d번 풀에 추가 완료.", i + 1)
    logger.info("브라우저 풀 초기화 완료. 현재 풀 크기: %d", BROWSER_POOL.qsize())

def _is_connected(browser: Browser) -> bool:
    try:
        return bool(browser) and browser.is_connected()
    except Exception:
        return False

async def get_browser_safe() -> Browser:
    """
    풀에서 브라우저를 하나 꺼내되,
    끊어진 브라우저면 즉시 폐기하고 새로 만들어서 반환.
    """
    while True:
        browser = await BROWSER_POOL.get()
        if _is_connected(browser):
            return browser
        # 죽은 브라우저는 정리 후 새로 보충
        try:
            await browser.close()
        except Exception:
            pass
        browser = await _launch_browser()
        # 새로 만든 것은 그대로 반환 (풀 보충은 put_browser_safe가 담당)

async def put_browser_safe(browser: Browser):
    """
    반납 시에도 살아있지 않으면 폐기하고 새로 보충하여 풀 크기 유지.
    """
    if _is_connected(browser):
        try:
            await BROWSER_POOL.put(browser)
            return
        except Exception:
            pass
    # 여기로 오면 브라우저가 고장났거나 put 실패 → 새로 보충
    try:
        if browser:
            await browser.close()
    except Exception:
        pass
    fresh = await _launch_browser()
    await BROWSER_POOL.put(fresh)

class PlaywrightJobConfig(AppConfig):
    name = "playwright_job"
    verbose_name = "Playwright Job"

    def ready(self):
        # runserver 리로더 부모 프로세스에서 중복 실행 방지
        if os.environ.get("RUN_MAIN") != "true":
            return

        loop = asyncio.get_event_loop()
        loop.create_task(init_browser_pool())
