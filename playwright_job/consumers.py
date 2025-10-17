import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

from .apps import get_browser_safe, put_browser_safe
from .tasks import run_playwright_task  # 시그니처: (browser, cert_date, test_no) -> {"url": ...}

logger = logging.getLogger(__name__)

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    """
    요청별 WebSocket: 한 커넥션 = 한 작업
    - 클라이언트가 첫 메시지로 {"인증일자": "...", "시험번호": "..."} 전송
    - 작업 완료/오류 시 응답 보내고 소켓을 닫음
    """

    async def connect(self):
        await self.accept()
        self._task = None

    async def disconnect(self, code):
        # 백그라운드 작업이 살아있다면 취소
        if self._task and not self._task.done():
            self._task.cancel()

    async def receive(self, text_data):
        # 첫 메시지에서만 작업을 시작하고, 그 이후 프레임은 무시
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            await self.send(text_data=json.dumps({"status": "error", "message": "잘못된 요청 데이터"}))
            await self.close()
            return

        cert_date = (payload.get("인증일자") or "").strip()
        test_no   = (payload.get("시험번호") or "").strip()

        if not cert_date or not test_no:
            await self.send(text_data=json.dumps({"status": "error", "message": "인증일자/시험번호가 누락되었습니다."}))
            await self.close()
            return

        async def run_one():
            browser = await get_browser_safe()
            try:
                # 진행중 알림(선택)
                await self.send(text_data=json.dumps({"status": "processing", "message": "Playwright 작업을 시작합니다."}))
                # tasks는 브라우저에서 컨텍스트/페이지를 스스로 생성하고 정리함
                # 필요 시 타임아웃 조정
                result = await asyncio.wait_for(
                    run_playwright_task(browser, cert_date, test_no),
                    timeout=180
                )
                url = (result or {}).get("url")
                if not url:
                    raise RuntimeError("URL 생성 실패")
                await self.send(text_data=json.dumps({"status": "success", "url": url}))
            except asyncio.CancelledError:
                await self.send(text_data=json.dumps({"status": "error", "message": "작업이 취소되었습니다."}))
                raise
            except Exception as e:
                logger.exception("작업 실패: %s", e)
                await self.send(text_data=json.dumps({"status": "error", "message": f"오류가 발생했습니다: {e}"}))
            finally:
                # 브라우저는 항상 반납(끊겼으면 put이 내부적으로 교체)
                await put_browser_safe(browser)
                # 요청별 WS: 작업 종료 후 소켓 닫기
                try:
                    await self.close()
                except Exception:
                    pass

        # 백그라운드로 실행
        self._task = asyncio.create_task(run_one())
