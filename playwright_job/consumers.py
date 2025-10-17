import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from .apps import get_browser_safe, put_browser_safe
from .tasks import run_playwright_task

logger = logging.getLogger(__name__)

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 헬로 프레임: 라우팅/컨슈머가 진입했는지 즉시 확인용
        await self.accept()
        try:
            await self.send(text_data=json.dumps({
                "status": "hello",
                "message": "Connected to PlaywrightJobConsumer"
            }))
        except Exception:
            pass
        self._task = None

    async def disconnect(self, code):
        if self._task and not self._task.done():
            self._task.cancel()

    async def receive(self, text_data=None, bytes_data=None):
        # 클라이언트가 실제로 프레임을 보낸 시점에 들어오는지 확인용 에코
        try:
            logger.warning("[WS] receive() called. raw=%s", (text_data or "")[:120])
        except Exception:
            pass

        # JSON 파싱
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            await self.send(text_data=json.dumps({"status": "error", "message": "잘못된 요청 데이터(JSON)"}))
            await self.close()
            return

        cert_date = (payload.get("인증일자") or "").strip()
        test_no   = (payload.get("시험번호") or "").strip()
        if not cert_date or not test_no:
            await self.send(text_data=json.dumps({"status": "error", "message": "인증일자/시험번호가 누락되었습니다."}))
            await self.close()
            return

        async def run_one():
            # 0) 먼저 대기 안내(프론트 로딩 표시용)
            try:
                await self.send(text_data=json.dumps({"status": "wait", "message": "브라우저를 기다리는 중..."}))
            except Exception:
                pass

            # 1) 브라우저 확보(게으른 확보 + 타임아웃)
            try:
                print(f"[WS] get_browser_safe START: {cert_date} {test_no}")
                browser = await asyncio.wait_for(get_browser_safe(), timeout=30)
                print(f"[WS] get_browser_safe OK: {cert_date} {test_no}")
            except asyncio.TimeoutError:
                await self.send(text_data=json.dumps({
                    "status": "error",
                    "message": "브라우저 확보 타임아웃(30s). 서버의 브라우저 풀 상태를 확인하세요."
                }))
                await self.close()
                return
            except Exception as e:
                await self.send(text_data=json.dumps({
                    "status": "error",
                    "message": f"브라우저 확보 실패: {e}"
                }))
                await self.close()
                return

            # 2) 실제 작업
            try:
                await self.send(text_data=json.dumps({"status": "processing", "message": "Playwright 작업 시작"}))
                print(f"[WS] run_playwright_task ENTER: {cert_date} {test_no}")
                result = await asyncio.wait_for(run_playwright_task(browser, cert_date, test_no), timeout=120)
                print(f"[WS] run_playwright_task DONE: {result}")
                url = (result or {}).get("url")
                if not url:
                    raise RuntimeError("URL 생성 실패")
                await self.send(text_data=json.dumps({"status": "success", "url": url}))
            except asyncio.TimeoutError:
                await self.send(text_data=json.dumps({"status": "error", "message": "작업 타임아웃(120s)"}))
            except Exception as e:
                logger.exception("[WS] 작업 실패 (%s %s): %s", cert_date, test_no, e)
                await self.send(text_data=json.dumps({"status": "error", "message": f"오류: {e}"}))
            finally:
                try:
                    await put_browser_safe(browser)
                except Exception as e:
                    logger.exception("[WS] put_browser_safe 실패: %s", e)
                try:
                    await self.close()
                except Exception:
                    pass

        self._task = asyncio.create_task(run_one())
