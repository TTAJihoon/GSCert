import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from .apps import get_browser_safe, put_browser_safe
from .tasks import run_playwright_task

logger = logging.getLogger(__name__)

# ---------------- 전역 작업 큐 + 단일 워커 ----------------

_job_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None
_worker_lock = asyncio.Lock()


async def _ensure_worker_started():
    """
    전역 ECM 워커를 한 번만 띄우기 위한 헬퍼.
    (프로세스 내에서 최초 요청 시 한 번만 실행)
    """
    global _job_queue, _worker_task
    async with _worker_lock:
        if _job_queue is None:
            _job_queue = asyncio.Queue()
            logger.warning("[WORKER] 전역 작업 큐 생성")

        if _worker_task is None or _worker_task.done():
            _worker_task = asyncio.create_task(_worker_loop())
            logger.warning("[WORKER] ECM 워커 태스크 시작")


async def enqueue_playwright_job(cert_date: str, test_no: str) -> dict:
    """
    (cert_date, test_no)를 전역 큐에 넣고, 해당 작업의 결과를 기다린 뒤 반환합니다.
    """
    await _ensure_worker_started()

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    await _job_queue.put({
        "cert_date": cert_date,
        "test_no": test_no,
        "future": fut,
    })
    logger.warning("[WORKER] 작업 enqueue: %s %s (queue size=%s)", cert_date, test_no, _job_queue.qsize())

    # 워커가 결과를 set_result/set_exception 할 때까지 대기
    return await fut


async def _worker_loop():
    """
    전역 ECM 워커:
    - get_browser_safe() 로 브라우저 확보
    - run_playwright_task() 실행
    - OS 클립보드 사용 포함 모든 Playwright 동작을 '항상 한 번에 하나'만 처리
    """
    global _job_queue
    logger.warning("[WORKER] ECM 워커 루프 시작")

    while True:
        job = await _job_queue.get()
        cert_date = job.get("cert_date")
        test_no = job.get("test_no")
        fut: asyncio.Future = job.get("future")

        logger.warning("[WORKER] 작업 시작: %s %s", cert_date, test_no)

        browser = None
        try:
            # 1) 브라우저 확보 (기존과 동일한 30s 타임아웃)
            logger.warning("[WORKER] get_browser_safe 대기: %s %s", cert_date, test_no)
            browser = await asyncio.wait_for(get_browser_safe(), timeout=30)
            logger.warning("[WORKER] get_browser_safe OK: %s %s", cert_date, test_no)

            # 2) 실제 Playwright 작업 실행 (기존 120s 타임아웃 유지)
            logger.warning("[WORKER] run_playwright_task ENTER: %s %s", cert_date, test_no)
            result = await asyncio.wait_for(run_playwright_task(browser, cert_date, test_no), timeout=120)
            logger.warning("[WORKER] run_playwright_task DONE: %s %s → %s", cert_date, test_no, result)

            # 3) 요청자에게 결과 전달
            if fut is not None and not fut.cancelled():
                fut.set_result(result)
            else:
                logger.warning("[WORKER] Future가 이미 취소/종료됨: %s %s", cert_date, test_no)

        except asyncio.TimeoutError as e:
            logger.exception("[WORKER] 작업 타임아웃: %s %s: %s", cert_date, test_no, e)
            if fut is not None and not fut.cancelled():
                fut.set_exception(e)
        except Exception as e:
            logger.exception("[WORKER] 작업 실패: %s %s: %s", cert_date, test_no, e)
            if fut is not None and not fut.cancelled():
                fut.set_exception(e)
        finally:
            if browser is not None:
                try:
                    await put_browser_safe(browser)
                except Exception as e:
                    logger.exception("[WORKER] put_browser_safe 실패: %s", e)

            _job_queue.task_done()
            logger.warning("[WORKER] 작업 완료 처리: %s %s (queue size=%s)", cert_date, test_no, _job_queue.qsize())


# ---------------- WebSocket Consumer ----------------

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
        self._task: asyncio.Task | None = None

    async def disconnect(self, code):
        # 이 컨슈머에서 실행 중인 로컬 태스크만 취소 (전역 워커는 계속 유지)
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
                await self.send(text_data=json.dumps({"status": "wait", "message": "ECM 작업 큐에 등록 중..."}))
            except Exception:
                pass

            try:
                # 전역 워커 보장 + 큐 enqueue
                await self.send(text_data=json.dumps({"status": "processing", "message": "ECM 작업 대기/실행 중..."}))
                result = await enqueue_playwright_job(cert_date, test_no)

                url = (result or {}).get("url")
                if not url:
                    raise RuntimeError("URL 생성 실패")

                await self.send(text_data=json.dumps({"status": "success", "url": url}))

            except asyncio.TimeoutError as e:
                logger.exception("[WS] 작업 타임아웃 (%s %s): %s", cert_date, test_no, e)
                user_msg = f"{test_no}의 ECM 불러오기를 실패하였습니다. 다시 요청해주세요."
                await self.send(text_data=json.dumps({
                    "status": "error",
                    "message": user_msg,
                }))
            except Exception as e:
                logger.exception("[WS] 작업 실패 (%s %s): %s", cert_date, test_no, e)
                user_msg = f"{test_no}의 ECM 불러오기를 실패하였습니다. 다시 요청해주세요."
                await self.send(text_data=json.dumps({
                    "status": "error",
                    "message": user_msg,
                }))
            finally:
                try:
                    await self.close()
                except Exception:
                    pass

        # 이 컨슈머 인스턴스 전용 태스크
        self._task = asyncio.create_task(run_one())
