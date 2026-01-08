import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

from .apps import get_browser_safe
from .tasks import run_playwright_task_on_page, StepError

logger_ws = logging.getLogger("playwright_job.ws")
logger_worker = logging.getLogger("playwright_job.worker")

_job_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None
_worker_lock = asyncio.Lock()


def _get_client_ip(scope) -> str:
    client = scope.get("client")
    if isinstance(client, (list, tuple)) and client:
        return client[0]
    return "-"


async def _ensure_worker_started():
    global _job_queue, _worker_task
    async with _worker_lock:
        if _job_queue is None:
            _job_queue = asyncio.Queue()
            logger_worker.info("ECM worker queue created")

        if _worker_task is None or _worker_task.done():
            _worker_task = asyncio.create_task(_worker_loop())
            logger_worker.info("ECM worker started")


async def enqueue_playwright_job(cert_date: str, test_no: str, request_ip: str) -> dict:
    await _ensure_worker_started()

    fut = asyncio.get_running_loop().create_future()
    await _job_queue.put({
        "cert_date": cert_date,
        "test_no": test_no,
        "request_ip": request_ip,
        "future": fut,
    })
    return await fut


async def _worker_loop():
    global _job_queue

    browser = None
    ecm_context = None
    ecm_page = None

    while True:
        job = await _job_queue.get()
        cert_date = job["cert_date"]
        test_no = job["test_no"]
        request_ip = job.get("request_ip", "-")
        fut: asyncio.Future = job["future"]

        try:
            if browser is None:
                browser = await asyncio.wait_for(get_browser_safe(), timeout=30)

            if ecm_context is None or ecm_page is None:
                ecm_context = await browser.new_context()
                ecm_page = await ecm_context.new_page()

            # ✅ step 로그/스크린샷/실패 한줄 로그는 tasks.py가 담당
            result = await asyncio.wait_for(
                run_playwright_task_on_page(
                    ecm_page,
                    cert_date,
                    test_no,
                    request_ip=request_ip,
                ),
                timeout=120,
            )
            if not fut.cancelled():
                fut.set_result(result)

        except StepError as e:
            # ✅ traceback 금지 / tasks.py에서 이미 한줄 로그 남김
            if not fut.cancelled():
                fut.set_exception(e)

            # 세션/DOM 꼬였을 수 있으니 reset
            try:
                if ecm_context:
                    await ecm_context.close()
            except Exception:
                pass
            ecm_context, ecm_page = None, None

        except asyncio.TimeoutError:
            # ✅ timeout도 StepError로 통일해서 올리는 편이 WS가 더 단순해짐
            # (tasks.py에서 99로 처리해도 되고, 여기서 만들어도 됨)
            e = StepError(step_no=98, error_kind="작업 타임아웃", screenshot="-", request_ip=request_ip)
            if not fut.cancelled():
                fut.set_exception(e)

            try:
                if ecm_context:
                    await ecm_context.close()
            except Exception:
                pass
            ecm_context, ecm_page = None, None

        except Exception:
            # ✅ 예상 밖 오류도 StepError로 통일
            e = StepError(step_no=99, error_kind="워커 오류", screenshot="-", request_ip=request_ip)
            if not fut.cancelled():
                fut.set_exception(e)

            try:
                if ecm_context:
                    await ecm_context.close()
            except Exception:
                pass
            ecm_context, ecm_page = None, None

        finally:
            _job_queue.task_done()


class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # 꼭 필요하면 한 줄만
        logger_ws.info("WS connected")

    async def disconnect(self, code):
        logger_ws.info("WS disconnected code=%s", code)

    async def receive(self, text_data=None, bytes_data=None):
        # 1) JSON 파싱
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            await self.send(text_data=json.dumps({"status": "error", "message": "JSON 형식 오류"}, ensure_ascii=False))
            await self.close()
            return

        cert_date = (payload.get("인증일자") or "").strip()
        test_no = (payload.get("시험번호") or "").strip()
        if not cert_date or not test_no:
            await self.send(text_data=json.dumps({"status": "error", "message": "인증일자/시험번호 누락"}, ensure_ascii=False))
            await self.close()
            return

        request_ip = _get_client_ip(self.scope)

        # 2) 실행
        try:
            await self.send(text_data=json.dumps({"status": "processing"}, ensure_ascii=False))

            result = await enqueue_playwright_job(cert_date, test_no, request_ip=request_ip)
            url = (result or {}).get("url")
            if not url:
                raise StepError(step_no=99, error_kind="URL 생성 실패", screenshot="-", request_ip=request_ip)

            await self.send(text_data=json.dumps({"status": "success", "url": url}, ensure_ascii=False))

        except StepError as e:
            # ✅ traceback 금지 / 필요한 정보만 클라이언트에게
            await self.send(text_data=json.dumps({
                "status": "error",
                "step": e.step_no,
                "error_kind": e.error_kind,
                "screenshot": e.screenshot,
                "message": f"{test_no} ECM 불러오기 실패. 스크린샷을 확인하세요.",
            }, ensure_ascii=False))

        finally:
            await self.close()
