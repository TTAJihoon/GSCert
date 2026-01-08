# myproject/playwright_job/consumers.py
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from channels.generic.websocket import AsyncWebsocketConsumer

from .apps import get_browser_safe
from .tasks import run_playwright_task_on_page, StepError

logger_ws = logging.getLogger("playwright_job.ws")
logger_worker = logging.getLogger("playwright_job.worker")

# ---------------- 전역 큐 + 단일 워커 ----------------
_job_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_worker_lock = asyncio.Lock()


async def _ensure_worker_started() -> None:
    """프로세스 내 전역 큐/워커를 1회만 생성"""
    global _job_queue, _worker_task
    async with _worker_lock:
        if _job_queue is None:
            _job_queue = asyncio.Queue()
            logger_worker.info("queue_init")

        if _worker_task is None or _worker_task.done():
            _worker_task = asyncio.create_task(_worker_loop())
            logger_worker.info("worker_started")


async def enqueue_playwright_job(cert_date: str, test_no: str, request_ip: str) -> Dict[str, Any]:
    """
    작업을 전역 큐에 넣고 결과를 기다려 반환.
    반환 dict:
      - result: 작업 결과(dict)
      - queue_ahead: enqueue 시점 내 앞 대기 수
      - queue_position: enqueue 시점 내 순번(대략)
      - queue_total: enqueue 시점 큐 총량(대략=position)
    """
    await _ensure_worker_started()
    assert _job_queue is not None

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    queue_ahead = _job_queue.qsize()
    queue_position = queue_ahead + 1
    queue_total = queue_position  # enqueue 시점 기준(대략)

    await _job_queue.put(
        {
            "cert_date": cert_date,
            "test_no": test_no,
            "request_ip": request_ip,
            "future": fut,
        }
    )

    result = await fut  # worker가 set_result / set_exception
    return {
        "result": result,
        "queue_ahead": queue_ahead,
        "queue_position": queue_position,
        "queue_total": queue_total,
    }


async def _worker_loop() -> None:
    """
    단일 워커:
      - browser 1회 확보 후 재사용
      - context/page 유지(로그인 탭 유지)
      - 작업은 항상 1개씩 처리
      - 실패 시 context/page reset
    """
    global _job_queue
    assert _job_queue is not None

    browser = None
    ecm_context = None
    ecm_page = None

    while True:
        job = await _job_queue.get()
        cert_date = job.get("cert_date")
        test_no = job.get("test_no")
        request_ip = job.get("request_ip", "-")
        fut: asyncio.Future = job.get("future")

        try:
            # 1) 브라우저 확보(최초 1회)
            if browser is None:
                browser = await asyncio.wait_for(get_browser_safe(), timeout=30)
                logger_worker.info("browser_ready")

            # 2) context/page 확보(최초 1회 또는 reset 후)
            if ecm_context is None or ecm_page is None:
                ecm_context = await browser.new_context()
                ecm_page = await ecm_context.new_page()
                logger_worker.info("context_page_ready")

            # 3) 실제 작업 실행
            #    - tasks.py에서 step 단위로 스크린샷/간단 로그 남김
            #    - consumers/worker에서는 traceback 남발 금지
            result = await asyncio.wait_for(
                run_playwright_task_on_page(
                    ecm_page,
                    cert_date,
                    test_no,
                    request_ip=request_ip,
                ),
                timeout=120,
            )

            if fut is not None and not fut.cancelled():
                fut.set_result(result)

        except Exception as e:
            # consumers.py에서는 traceback를 길게 찍지 않음(요구사항)
            # StepError면 step/screenshot 정보를 유지해서 그대로 올려보냄
            if fut is not None and not fut.cancelled():
                fut.set_exception(e)

            # 실패 시 세션/화면 상태가 꼬였을 가능성이 크므로 reset
            try:
                if ecm_context is not None:
                    await ecm_context.close()
            except Exception:
                pass
            ecm_context, ecm_page = None, None
            logger_worker.warning("context_page_reset")

        finally:
            _job_queue.task_done()


# ---------------- WebSocket Consumer ----------------

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # 연결 로그는 최소만
        logger_ws.info("ws_connect ip=%s", self._client_ip())

        # 프론트 로그에서 hello를 기대하고 있길래 유지(불필요하면 제거 가능)
        await self._safe_send({"status": "hello", "message": "Connected to PlaywrightJobConsumer"})

    async def disconnect(self, code):
        logger_ws.info("ws_disconnect ip=%s code=%s", self._client_ip(), code)

    def _client_ip(self) -> str:
        client = self.scope.get("client")
        if not client:
            return "-"
        return client[0] or "-"

    async def _safe_send(self, payload: Dict[str, Any]) -> None:
        try:
            await self.send(text_data=json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        request_ip = self._client_ip()

        # 1) JSON 파싱
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            await self._safe_send({"status": "error", "message": "잘못된 요청 데이터(JSON)"})
            await self.close()
            return

        cert_date = (payload.get("인증일자") or "").strip()
        test_no = (payload.get("시험번호") or "").strip()
        if not cert_date or not test_no:
            await self._safe_send({"status": "error", "message": "인증일자/시험번호가 누락되었습니다."})
            await self.close()
            return

        # 2) enqueue 시점 큐 정보(대략)
        try:
            await _ensure_worker_started()
            assert _job_queue is not None
            queue_ahead = _job_queue.qsize()
            queue_position = queue_ahead + 1
            queue_total = queue_position

            await self._safe_send(
                {
                    "status": "wait",
                    "message": "ECM 작업 큐에 등록 중...",
                    "queue_ahead": queue_ahead,
                    "queue_position": queue_position,
                    "queue_total": queue_total,
                }
            )
        except Exception:
            # 큐 상태 조회 실패해도 작업은 시도
            await self._safe_send({"status": "wait", "message": "ECM 작업 큐에 등록 중..."})

        # 3) 실행 안내(실제 시작 시점이 아니라 “대기/실행 흐름” 안내용)
        await self._safe_send({"status": "processing", "message": "ECM 작업 대기/실행 중..."})

        # 4) 작업 수행(완료까지 WS 유지 후 종료)
        try:
            pack = await enqueue_playwright_job(cert_date, test_no, request_ip=request_ip)
            result = (pack or {}).get("result") or {}
            url = result.get("url")

            if not url:
                raise RuntimeError("URL 생성 실패")

            await self._safe_send({"status": "success", "url": url})

        except StepError as e:
            # tasks.py가 이미 한 줄 로그를 남김(시간|IP|S#|오류종류|스크린샷)
            # 프론트에는 간단 메시지 + 디버그 최소 정보만(선택)
            await self._safe_send(
                {
                    "status": "error",
                    "message": f"{test_no}의 ECM 불러오기를 실패하였습니다. 다시 요청해주세요.",
                    "step": getattr(e, "step_no", None),
                    "error_kind": getattr(e, "error_kind", None),
                    "screenshot": getattr(e, "screenshot", None),
                }
            )

        except Exception:
            # consumers.py에서는 traceback 로그 남발 금지
            await self._safe_send(
                {
                    "status": "error",
                    "message": f"{test_no}의 ECM 불러오기를 실패하였습니다. 다시 요청해주세요.",
                }
            )

        finally:
            try:
                await self.close()
            except Exception:
                pass
