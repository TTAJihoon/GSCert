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
    - 첫 메시지로 {"인증일자": "...", "시험번호": "..."} 수신
    - tasks가 브라우저에서 컨텍스트/페이지를 생성/정리
    - 완료/오류 응답을 보낸 뒤 소켓을 닫음
    """

    async def connect(self):
        await self.accept()
        self._task = None

    async def disconnect(self, code):
        if self._task and not self._task.done():
            self._task.cancel()

    async def receive(self, text_data):
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
        # 1) 먼저 대기 안내 전송 → 프런트에서 loadingIndicator 표시용
        await self.send(text_data=json.dumps({
            "status": "wait",
            "message": "사용 가능한 브라우저를 기다리는 중입니다..."
        }))

        # 2) 브라우저 획득 (풀 미초기화/장애 대비 타임아웃)
        try:
            browser = await asyncio.wait_for(get_browser_safe(), timeout=30)
        except asyncio.TimeoutError:
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": "브라우저 풀을 초기화하지 못했습니다. 서버 로그를 확인해주세요."
            }))
            await self.close()
            return

        try:
            # 3) 실제 작업 시작 안내
            await self.send(text_data=json.dumps({
                "status": "processing",
                "message": "Playwright 작업을 시작합니다."
            }))

            # 4) tasks는 내부에서 context/page 생성 및 정리 수행
            result = await asyncio.wait_for(
                run_playwright_task(browser, cert_date, test_no),
                timeout=180  # 필요 시 조정
            )

            url = (result or {}).get("url")
            if not url:
                raise RuntimeError("URL 생성 실패")

            # 5) 성공 응답
            await self.send(text_data=json.dumps({
                "status": "success",
                "url": url
            }))

        except asyncio.CancelledError:
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": "작업이 취소되었습니다."
            }))
            raise
        except Exception as e:
            logger.exception("작업 실패: %s", e)
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": f"오류가 발생했습니다: {e}"
            }))
        finally:
            # 6) 브라우저 반납(끊겼으면 put이 내부적으로 교체), 소켓 종료
            await put_browser_safe(browser)
            try:
                await self.close()   # 요청별 WS: 작업 종료 후 소켓 닫기
            except Exception:
                pass
