import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from .apps import get_browser_safe, put_browser_safe  # ★ 새 유틸 사용

logger = logging.getLogger(__name__)

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.task = None

    async def disconnect(self, code):
        if self.task and not self.task.done():
            self.task.cancel()

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except Exception:
            await self.send(text_data=json.dumps({"status": "error", "message": "잘못된 요청"}))
            return

        # 사용자가 보내는 키 예: {"인증일자": "...", "시험번호": "..."}
        async def run_one():
            browser = await get_browser_safe()
            try:
                # 고장난 브라우저 방어: new_context 1회 재시도
                try:
                    context = await browser.new_context()
                except Exception as e:
                    logger.warning("new_context 실패, 1회 재시도: %s", e)
                    await put_browser_safe(browser)      # 고장났을 수 있으니 즉시 반납(교체)
                    browser = await get_browser_safe()   # 새로 받아서 재시도
                    context = await browser.new_context()

                page = await context.new_page()
                try:
                    # 진행 중 알림(선택)
                    await self.send(text_data=json.dumps({"status": "processing", "message": "Playwright 작업을 시작합니다."}))
                    # ---- 실제 작업 호출 (기존 tasks 함수) ----
                    from .tasks import run_playwright_task
                    result = await run_playwright_task(page, payload)
                    # ----------------------------------------
                    await self.send(text_data=json.dumps({"status": "success", "url": result["url"]}))
                finally:
                    await context.close()
            except asyncio.CancelledError:
                await self.send(text_data=json.dumps({"status": "error", "message": "취소되었습니다."}))
                raise
            except Exception as e:
                logger.exception("작업 실패: %s", e)
                await self.send(text_data=json.dumps({"status": "error", "message": f"오류가 발생했습니다: {e}"}))
            finally:
                await put_browser_safe(browser)

        # 백그라운드 태스크로 실행
        self.task = asyncio.create_task(run_one())
