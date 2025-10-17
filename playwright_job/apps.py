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
    """단일 Playwright 핸들에서 브라우저 하나를 띄운다."""
    global _playwright
    if _playwright is None:
        _playwright = await async_playwright().start()
    # 필요에 따라 chromium/firefox/webkit 선택
    browser = await _playwright.chromium.launch(headless=True)
    return browser

def _is_connected(browser: Browser) -> bool:
    try:
        return bool(browser) and browser.is_connected()
    except Exception:
        return False

async def init_browser_pool():
    """앱 기동 시 브라우저 풀을 미리 채운다."""
    logger.warning(">>> 브라우저 풀 초기화 시작")
    for i in range(POOL_SIZE):
        b = await _launch_browser()
        await BROWSER_POOL.put(b)
        logger.warning("브라우저 %d번 풀에 추가 완료", i + 1)
    logger.warning("브라우저 풀 초기화 완료. 현재 풀 크기: %d", BROWSER_POOL.qsize())

async def get_browser_safe() -> Browser:
    """
    풀에서 하나 꺼내되, 끊어진 브라우저면 폐기하고 새로 만들어 반환.
    (풀은 put_browser_safe가 보충)
    """
    while True:
        browser = await BROWSER_POOL.get()
        if _is_connected(browser):
            return browser
        try:
            await browser.close()
        except Exception:
            pass
        # 끊어진 브라우저는 새로 교체
        browser = await _launch_browser()
        return browser  # 풀 보충은 put_browser_safe에서 수행

async def put_browser_safe(browser: Browser):
    """
    반납 시에도 끊어져 있으면 새로 보충하여 풀 크기 유지.
    """
    try:
        if _is_connected(browser):
            await BROWSER_POOL.put(browser)
            return
    except Exception:
        pass
    # 여기까지 왔으면 끊김 → 폐기 후 새로 보충
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
