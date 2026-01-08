import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

from .apps import get_browser_safe
from .tasks import run_playwright_task_on_page

logger_ws = logging.getLogger("playwright_job.ws")
logger_worker = logging.getLogger("playwright_job.worker")

_job_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None
_worker_lock = asyncio.Lock()


async def _ensure_worker_started():
    global _job_queue, _worker_task
    async with _worker_lock:
        if _job_queue is None:
            _job_queue = asyncio.Queue()

        if _worker_task is None or _worker_task.done():
            _worker_task = asyncio.create_task(_worker_loop())


async def enqueue_playwright_job(cert_date: str, test_no: str, request_ip: str) -> dict:
    """
    결과 future + 시작 알림 future 를 같이 만들어서 반환
    queue_position은 enqueue 시점의 qsize+1 스냅샷(대략치)
    """
    await _ensure_worker_started()
    assert _job_queue is not None

    loop = asyncio.get_running_loop()
    result_fut: asyncio.Future = loop.create_future()
    started_fut: asyncio.Future = loop.create_future()

    queue_size_now = _job_queue.qsize()
    queue_position = queue_size_now + 1
    queue_total = queue_size_now + 1  # "대기열 총량"을 같은 의미로 쓰고 싶으면 이렇게(대략)

    await _job_queue.put({
        "cert_date": cert_date,
        "test_no": test_no,
        "request_ip": request_ip,
        "started_future": started_fut,
        "result_future": result_fut,
    })

    return {
        "queue_position": queue_position,
        "queue_total": queue_total,
        "started_future": started_fut,
        "result_future": result_fut,
    }


async def _worker_loop():
    global _job_queue
    logger_worker.info("ECM worker loop started")

    browser = None
    ecm_context = None
    ecm_page = None

    assert _job_queue is not None

    while True:
        job = await _job_queue.get()

        cert_date = job["cert_date"]
        test_no = job["test_no"]
        request_ip = job.get("request_ip", "-")

        started_fut: asyncio.Future = job["started_future"]
        result_fut: asyncio.Future = job["result_future"]

        try:
            # 워커가 실제로 이 job을 잡았음을 알림 (processing 타이밍)
            if not started_fut.done():
                started_fut.set_result(True)

            # 브라우저/세션 준비
            if browser is None:
                browser = await asyncio.wait_for(get_browser_safe(), timeout=30)

            if ecm_context is None or ecm_page is None:
                ecm_context = await browser.new_context()
                ecm_page = await ecm_context.new_page()

            # 실제 작업
            result = await asyncio.wait_for(
                run_playwright_task_on_page(ecm_page, cert_date, test_no, request_ip=request_ip),
                timeout=120,
            )

            if not result_fut.cancelled():
                result_fut.set_result(result)

        except Exception as e:
            # tasks.py 쪽에서 StepError로 이미 “한 줄 로그 + 스샷” 찍는 정책이므로
            # 여기서는 traceback 굳이 안 찍고 결과만 error로 넘기는 편이 깔끔함
            if not result_fut.cancelled():
                result_fut.set_exception(e)

            # 세션 꼬였을 가능성 → context reset
            try:
                if ecm_context is not None:
                    await ecm_context.close()
            except Exception:
                pass
            ecm_context, ecm_page = None, None

        finally:
            _job_queue.task_done()


class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # hello는 유지해도 되고(디버깅용), 싫으면 제거해도 됨
        await self.send(text_data=json.dumps({
            "status": "hello",
            "message": "Connected to PlaywrightJobConsumer"
        }))

    async def disconnect(self, code):
        logger_ws.info("WebSocket disconnected: code=%s", code)

    async def receive(self, text_data=None, bytes_data=None):
        # 요청 IP
        request_ip = "-"
        try:
            request_ip = (self.scope.get("client") or ["-"])[0] or "-"
        except Exception:
            request_ip = "-"

        # JSON 파싱
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": "잘못된 요청 데이터(JSON)"
            }))
            await self.close()
            return

        cert_date = (payload.get("인증일자") or "").strip()
        test_no = (payload.get("시험번호") or "").strip()
        if not cert_date or not test_no:
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": "인증일자/시험번호가 누락되었습니다."
            }))
            await self.close()
            return

        try:
            # 1) enqueue + 대기순번(대략) 반환
            enq = await enqueue_playwright_job(cert_date, test_no, request_ip=request_ip)

            await self.send(text_data=json.dumps({
                "status": "wait",
                "message": "ECM 작업 큐에 등록 중...",
                "queue_position": enq["queue_position"],
                "queue_total": enq["queue_total"],
            }))

            # 2) 워커가 실제로 내 작업을 꺼낸 순간에 processing
            await enq["started_future"]
            await self.send(text_data=json.dumps({
                "status": "processing",
                "message": "ECM 작업 실행 중...",
                "queue_position": enq["queue_position"],
                "queue_total": enq["queue_total"],
            }))

            # 3) 결과 대기
            result = await enq["result_future"]
            url = (result or {}).get("url")
            if not url:
                raise RuntimeError("URL 생성 실패")

            await self.send(text_data=json.dumps({
                "status": "success",
                "url": url
            }))

        except Exception:
            # 사용자 메시지는 단순하게
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": f"{test_no}의 ECM 불러오기를 실패하였습니다. 다시 요청해주세요."
            }))
        finally:
            # 너가 원한 정책: 요청 끝나면 close 유지
            try:
                await self.close()
            except Exception:
                pass
