import asyncio
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from .apps import get_browser_safe  # put_browser_safe는 더 이상 매 작업마다 쓰지 않음
from .tasks import run_playwright_task_on_page  # ★ 새 헬퍼 (tasks.py에 추가 필요)

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
    logger.warning(
        "[WORKER] 작업 enqueue: %s %s (queue size=%s)",
        cert_date,
        test_no,
        _job_queue.qsize(),
    )

    # 워커가 결과를 set_result/set_exception 할 때까지 대기
    return await fut


async def _worker_loop():
    """
    전역 ECM 워커:

    - get_browser_safe() 로 브라우저 확보 (최초 1회 또는 오류 시 재획득)
    - 로그인/초기화가 끝난 ECM 전용 context/page 를 유지
    - run_playwright_task_on_page() 를 호출해 각 작업을 '항상 한 번에 하나씩' 처리
    """
    global _job_queue
    logger.warning("[WORKER] ECM 워커 루프 시작")

    browser = None
    ecm_context = None
    ecm_page = None

    while True:
        job = await _job_queue.get()
        cert_date = job.get("cert_date")
        test_no = job.get("test_no")
        fut: asyncio.Future = job.get("future")

        logger.warning("[WORKER] 작업 시작: %s %s", cert_date, test_no)

        try:
            # 1) 브라우저 확보 (최초 1회 / 오류 시 재획득)
            if browser is None:
                logger.warning("[WORKER] get_browser_safe 대기: %s %s", cert_date, test_no)
                browser = await asyncio.wait_for(get_browser_safe(), timeout=30)
                logger.warning("[WORKER] get_browser_safe OK: %s %s", cert_date, test_no)

            # 2) ECM 전용 context/page 확보 (로그인 완료된 탭 유지용)
            if ecm_context is None or ecm_page is None:
                logger.warning("[WORKER] ECM context/page 생성")
                ecm_context = await browser.new_context()
                ecm_page = await ecm_context.new_page()
                # 여기서 필요하다면 ecm_page.goto(ECM_BASE_URL) + 로그인 루틴을
                # run_playwright_task_on_page 내부에서 처리하거나,
                # 별도 초기화 루틴으로 분리할 수 있음.
                logger.warning("[WORKER] ECM context/page 생성 완료")

            # 3) 실제 Playwright 작업 실행 (로그인/트리 탐색/URL 복사까지)
            logger.warning("[WORKER] run_playwright_task_on_page ENTER: %s %s", cert_date, test_no)
            result = await asyncio.wait_for(
                run_playwright_task_on_page(ecm_page, cert_date, test_no),
                timeout=120,
            )
            logger.warning(
                "[WORKER] run_playwright_task_on_page DONE: %s %s → %s",
                cert_date,
                test_no,
                result,
            )

            # 4) 요청자에게 결과 전달
            if fut is not None and not fut.cancelled():
                fut.set_result(result)
            else:
                logger.warning(
                    "[WORKER] Future가 이미 취소/종료됨: %s %s",
                    cert_date,
                    test_no,
                )

        except asyncio.TimeoutError as e:
            logger.exception("[WORKER] 작업 타임아웃: %s %s: %s", cert_date, test_no, e)
            if fut is not None and not fut.cancelled():
                fut.set_exception(e)

            # 타임아웃/에러 시 context/page는 깨졌을 수 있으니 재생성하도록 None 처리
            try:
                if ecm_context is not None:
                    await ecm_context.close()
            except Exception as ee:
                logger.exception("[WORKER] ECM context close 실패: %s", ee)
            ecm_context, ecm_page = None, None
            logger.warning("[WORKER] ECM context/page reset (Timeout)")

        except Exception as e:
            logger.exception("[WORKER] 작업 실패: %s %s: %s", cert_date, test_no, e)
            if fut is not None and not fut.cancelled():
                fut.set_exception(e)

            # 세션 만료/로그인 페이지 전환 등으로 의심되면 context/page 재생성
            try:
                if ecm_context is not None:
                    await ecm_context.close()
            except Exception as ee:
                logger.exception("[WORKER] ECM context close 실패: %s", ee)
            ecm_context, ecm_page = None, None
            logger.warning("[WORKER] ECM context/page reset (Exception)")

        finally:
            _job_queue.task_done()
            logger.warning(
                "[WORKER] 작업 완료 처리: %s %s (queue size=%s)",
                cert_date,
                test_no,
                _job_queue.qsize(),
            )

    # 이 루프는 일반적으로 종료되지 않으므로 browser/put_browser_safe는 여기서 다루지 않음.
    # 필요하면 종료 훅에서 browser를 반납/close하도록 확장 가능.


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
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": "잘못된 요청 데이터(JSON)"
            }))
            await self.close()
            return

        cert_date = (payload.get("인증일자") or "").strip()
        test_no   = (payload.get("시험번호") or "").strip()
        if not cert_date or not test_no:
            await self.send(text_data=json.dumps({
                "status": "error",
                "message": "인증일자/시험번호가 누락되었습니다."
            }))
            await self.close()
            return

        async def run_one():
            # 0) 먼저 대기 안내(프론트 로딩 표시용)
            try:
                await self.send(text_data=json.dumps({
                    "status": "wait",
                    "message": "ECM 작업 큐에 등록 중..."
                }))
            except Exception:
                pass

            try:
                # 전역 워커 보장 + 큐 enqueue
                await self.send(text_data=json.dumps({
                    "status": "processing",
                    "message": "ECM 작업 대기/실행 중..."
                }))
                result = await enqueue_playwright_job(cert_date, test_no)

                url = (result or {}).get("url")
                if not url:
                    raise RuntimeError("URL 생성 실패")

                await self.send(text_data=json.dumps({
                    "status": "success",
                    "url": url
                }))

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
