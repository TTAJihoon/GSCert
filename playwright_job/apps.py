import asyncio
import threading
import sys
import os
import platform
from django.apps import AppConfig
from playwright.async_api import async_playwright, Browser

BROWSER_POOL: "asyncio.Queue[Browser]" = asyncio.Queue(maxsize=5)
PLAYWRIGHT_INSTANCE = None
_INITIALIZED = False  # ready() 중복 호출(리로더 등) 방지 플래그


async def initialize_browsers():
    """
    서버 시작 시 브라우저 5개를 미리 띄워 풀에 넣는다.
    """
    global PLAYWRIGHT_INSTANCE
    print("Playwright 브라우저 풀 초기화를 시작합니다...")

    PLAYWRIGHT_INSTANCE = await async_playwright().start()
    browser_type = PLAYWRIGHT_INSTANCE.chromium

    for i in range(5):
        try:
            browser = await browser_type.launch(headless=True)
            await BROWSER_POOL.put(browser)
            print(f"브라우저 {i + 1}번 풀에 추가 완료.")
        except Exception as e:
            print(f"브라우저 {i + 1}번 실행 실패: {e}")

    print(f"브라우저 풀 초기화 완료. 현재 풀 크기: {BROWSER_POOL.qsize()}")


async def shutdown_browsers():
    """서버 종료 시 브라우저 정리"""
    print("Playwright 브라우저 풀을 종료합니다...")
    while not BROWSER_POOL.empty():
        browser = await BROWSER_POOL.get()
        await browser.close()
    if PLAYWRIGHT_INSTANCE:
        await PLAYWRIGHT_INSTANCE.stop()
    print("브라우저 풀 종료 완료.")


def _should_skip_init() -> bool:
    """
    관리 명령/테스트/명시적 스킵 환경에서 초기화를 건너뛸지 판단
    """
    if os.getenv("SKIP_BROWSER_INIT") == "1":
        return True

    mgmt_cmds_to_skip = {
        "collectstatic", "check", "migrate", "makemigrations",
        "shell", "showmigrations", "loaddata", "dumpdata", "test"
    }
    return any(cmd in sys.argv for cmd in mgmt_cmds_to_skip)


def _should_init_now() -> bool:
    """
    Django가 ready()를 두 번 호출하는 상황(리로더)에서 한 번만 초기화하도록 제어
    """
    # devserver의 자동 리로더 환경에서 메인 프로세스만 초기화
    run_main = os.getenv("RUN_MAIN")
    if run_main is not None and run_main.lower() != "true":
        return False
    return True


class PlaywrightJobConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "playwright_job"

    def ready(self):
        global _INITIALIZED

        # 1) 관리 명령/스킵 조건이면 즉시 반환 (collectstatic 포함)
        if _should_skip_init():
            return

        # 2) 리로더 등으로 인한 중복 초기화 방지
        if _INITIALIZED or not _should_init_now():
            return

        # 3) Windows에서는 subprocess가 가능한 Proactor 정책을 명시
        if platform.system() == "Windows":
            # ⚠️ 기존 코드의 WindowsSelectorEventLoopPolicy는 PLAYWRIGHT에 부적합
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # 4) 백그라운드 스레드에서 비동기 초기화 시작
        def _runner():
            # 새 스레드에서도 정책이 적용되어 있어야 함
            if platform.system() == "Windows":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            asyncio.run(initialize_browsers())

        threading.Thread(target=_runner, daemon=True).start()
        _INITIALIZED = True
