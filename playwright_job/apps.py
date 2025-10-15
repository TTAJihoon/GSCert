import asyncio
import threading
from django.apps import AppConfig
from playwright.async_api import async_playwright, Browser

# 동시에 5개의 브라우저를 담을 수 있는 '브라우저 보관함' (Queue)
BROWSER_POOL = asyncio.Queue(maxsize=5)
# Playwright 인스턴스를 전역으로 관리
PLAYWRIGHT_INSTANCE = None

async def initialize_browsers():
    """
    서버 시작 시 5개의 브라우저를 실행하여 풀에 추가하는 비동기 함수
    """
    global PLAYWRIGHT_INSTANCE
    print("Playwright 브라우저 풀 초기화를 시작합니다...")
    
    PLAYWRIGHT_INSTANCE = await async_playwright().start()
    browser_type = PLAYWRIGHT_INSTANCE.chromium

    for i in range(5):
        try:
            browser = await browser_type.launch(headless=True)
            await BROWSER_POOL.put(browser)
            print(f"브라우저 {i+1}번 풀에 추가 완료.")
        except Exception as e:
            print(f"브라우저 {i+1}번 실행 실패: {e}")
    
    print(f"브라우저 풀 초기화 완료. 현재 풀 크기: {BROWSER_POOL.qsize()}")

async def shutdown_browsers():
    """서버 종료 시 모든 브라우저를 닫고 Playwright를 종료하는 함수"""
    print("Playwright 브라우저 풀을 종료합니다...")
    while not BROWSER_POOL.empty():
        browser = await BROWSER_POOL.get()
        await browser.close()
    if PLAYWRIGHT_INSTANCE:
        await PLAYWRIGHT_INSTANCE.stop()
    print("브라우저 풀 종료 완료.")


class PlaywrightJobConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'playwright_job'

    def ready(self):
        """Django 앱이 준비되면 호출되는 메소드"""
        # ready()는 동기 메소드이므로, 비동기 초기화 함수를
        # 별도의 스레드에서 실행하여 메인 스레드를 막지 않도록 합니다.
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        if BROWSER_POOL.empty():
             # 백그라운드 스레드에서 비동기 함수 실행
            threading.Thread(target=lambda: asyncio.run(initialize_browsers()), daemon=True).start()

        # ※ 참고: 실제 프로덕션 환경에서는 서버 종료 시그널(cleanup)을 받아
        # shutdown_browsers()를 호출해주는 로직을 추가하면 더 좋습니다.

