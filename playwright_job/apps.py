import asyncio
import logging
from typing import Optional
from django.apps import AppConfig
from playwright.async_api import Browser  # ← Browser 타입만 남기고, async_playwright는 함수 안에서 import

logger = logging.getLogger(__name__)

# 원하는 풀 크기
POOL_SIZE = 5

# 큐(있으면 재사용, 없으면 즉시 새로 띄움)
BROWSER_POOL: asyncio.Queue[Browser] = asyncio.Queue(maxsize=POOL_SIZE)

# 전역 Playwright 핸들/락
_playwright = None
_playwright_lock = asyncio.Lock()

# ★ 누락되어 있던 플래그 선언 추가
_pool_warmup_started = False


async def _ensure_playwright_started():
    """전역 Playwright 런타임을 1회만 시작 (동시성 보호)."""
    global _playwright
    if _playwright is not None:
        return
    async with _playwright_lock:
        if _playwright is None:
            from playwright.async_api import async_playwright  # ← 여기서 import
            # 여기서도 혹시 모를 정책 누락 대비(중복무해)
            import sys, asyncio as _aio
            if sys.platform.startswith("win"):
                try:
                    _aio.set_event_loop_policy(_aio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass
            logger.warning(">>> Playwright 런타임 시작")
            _playwright = await async_playwright().start()


async def _launch_browser() -> Browser:
    """브라우저 하나 새로 띄움."""
    await _ensure_playwright_started()
    # 필요에 따라 firefox/webkit 변경 가능
    b = await _playwright.chromium.launch(headless=True)
    return b

def _is_connected(b: Optional[Browser]) -> bool:
    try:
        return bool(b) and b.is_connected()
    except Exception:
        return False

async def get_browser_safe() -> Browser:
    """
    항상 '살아있는' 브라우저를 반환.
    - 큐에 있으면 꺼내 검사
    - 큐가 비어있거나 끊겨 있으면 즉시 새로 띄워 반환 (게으른 확보)
    """
    try:
        b: Optional[Browser] = None
        if not BROWSER_POOL.empty():
            b = await BROWSER_POOL.get()
            if _is_connected(b):
                return b
            try:
                await b.close()
            except Exception:
                pass
        fresh = await _launch_browser()
        return fresh
    except Exception as e:
        logger.exception("get_browser_safe 실패: %s", e)
        # 최후의 보루
        fresh = await _launch_browser()
        return fresh

async def put_browser_safe(b: Optional[Browser]):
    """브라우저 반납. 살아있고 큐가 여유 있으면 큐에 되돌리고, 아니면 닫음."""
    try:
        if _is_connected(b):
            try:
                BROWSER_POOL.put_nowait(b)
                return
            except asyncio.QueueFull:
                pass
    except Exception:
        pass
    try:
        if b:
            await b.close()
    except Exception:
        pass

async def _warmup_pool():
    """(선택) 백그라운드 웜업: 있으면 큐를 목표 크기까지 채움."""
    global _pool_warmup_started
    if _pool_warmup_started:
        return
    _pool_warmup_started = True
    logger.warning(">>> 브라우저 풀 웜업 시작 (lazy)")
    try:
        while BROWSER_POOL.qsize() < POOL_SIZE:
            b = await _launch_browser()
            try:
                BROWSER_POOL.put_nowait(b)
            except asyncio.QueueFull:
                await b.close()
                break
        logger.warning("브라우저 풀 웜업 완료. 큐 크기: %d", BROWSER_POOL.qsize())
    except Exception as e:
        logger.exception("풀 웜업 실패: %s", e)
    finally:
        _pool_warmup_started = False

class PlaywrightJobConfig(AppConfig):
    name = "playwright_job"
    verbose_name = "Playwright Job"

    def ready(self):
        """
        ASGI/Daphne 환경의 라이프사이클과 무관하게 동작하도록
        풀은 요청 시점(get_browser_safe)에서 lazy 생성.
        여기서는 선택적으로 백그라운드 웜업만 시도한다.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_warmup_pool())
        except Exception:
            pass
