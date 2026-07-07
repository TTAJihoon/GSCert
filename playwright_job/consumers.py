# myproject/playwright_job/consumers.py
import asyncio
import json
import logging
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from main.utils.ecm_agent_lock import async_ecm_agent_lock

from .apps import get_browser_safe
from .tasks import run_playwright_task_on_page, run_document_download_on_page, StepError

logger_ws = logging.getLogger("playwright_job.ws")
logger_worker = logging.getLogger("playwright_job.worker")

# ---------------- 전역 큐 + 단일 워커 ----------------
# Playwright 는 Windows 에서 브라우저 하위 프로세스 실행에 ProactorEventLoop 가 필요하다.
# 그런데 이 서버(daphne/Channels)는 Twisted 호환을 위해 SelectorEventLoop 를 강제하므로
# ASGI 루프에서 직접 Playwright 를 띄우면 NotImplementedError 가 난다.
# → Playwright 워커를 '전용 ProactorEventLoop 스레드'에서 돌리고, ASGI 컨슈머는
#   run_coroutine_threadsafe + wrap_future 로 그 루프에 잡을 넘기고 결과를 받는다.
_job_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_worker_thread: Optional[threading.Thread] = None
_worker_loop_obj: Optional[asyncio.AbstractEventLoop] = None
_worker_ready = threading.Event()
_worker_start_lock = threading.Lock()

# ---------------- DB (ECM URL 캐시) ----------------
_db_lock = asyncio.Lock()
_db_mapping: Optional[Tuple[str, str, str]] = None  # (table, test_col, url_col)

_TEST_COL_CANDIDATES = ["시험번호", "test_no", "testNo", "TEST_NO"]
_URL_COL_CANDIDATES = ["URL", "url", "url주소", "URL주소", "주소", "link", "LINK"]


def _db_path() -> Path:
    # 사용자 지정 경로: main/data/ecmURL.db
    p = Path(settings.BASE_DIR) / "main" / "data" / "ecmURL.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _detect_table_and_cols(conn: sqlite3.Connection) -> Optional[Tuple[str, str, str]]:
    """
    DB에 이미 존재하는 테이블/컬럼명을 최대한 자동 탐지.
    - 시험번호 컬럼(시험번호/test_no 등) + URL 컬럼(URL/url 등)을 가진 테이블을 찾는다.
    """
    cur = conn.cursor()
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    for (tname,) in tables:
        cols = cur.execute(f"PRAGMA table_info('{tname}')").fetchall()
        colnames = [c[1] for c in cols]  # (cid, name, type, notnull, dflt_value, pk)

        test_col = next((c for c in colnames if c in _TEST_COL_CANDIDATES), None)
        url_col = next((c for c in colnames if c in _URL_COL_CANDIDATES), None)

        if test_col and url_col:
            return (tname, test_col, url_col)

    return None


def _ensure_table(conn: sqlite3.Connection) -> Tuple[str, str, str]:
    """
    1) 기존 테이블/컬럼 자동 탐지
    2) 없으면 기본 테이블 생성: ecm_url(test_no, url)
    """
    global _db_mapping

    if _db_mapping:
        return _db_mapping

    found = _detect_table_and_cols(conn)
    if found:
        _db_mapping = found
        return _db_mapping

    # 기본 테이블 생성(없을 때만)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ecm_url (
            test_no TEXT PRIMARY KEY,
            url     TEXT NOT NULL
        )
        """
    )
    conn.commit()
    _db_mapping = ("ecm_url", "test_no", "url")
    return _db_mapping


def _db_get_url_sync(test_no: str) -> Optional[str]:
    p = _db_path()
    conn = sqlite3.connect(str(p))
    try:
        table, test_col, url_col = _ensure_table(conn)
        cur = conn.cursor()
        row = cur.execute(
            f"SELECT {url_col} FROM {table} WHERE {test_col} = ?",
            (test_no,),
        ).fetchone()
        if not row:
            return None
        url = (row[0] or "").strip()
        return url or None
    finally:
        conn.close()


def _db_upsert_url_sync(test_no: str, url: str) -> None:
    p = _db_path()
    conn = sqlite3.connect(str(p))
    try:
        table, test_col, url_col = _ensure_table(conn)
        # SQLite 버전 호환을 위해 INSERT OR REPLACE 사용
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({test_col}, {url_col}) VALUES (?, ?)",
            (test_no, url),
        )
        conn.commit()
    finally:
        conn.close()


async def db_get_url(test_no: str) -> Optional[str]:
    # sqlite3는 sync라 event loop 블로킹 방지
    async with _db_lock:
        return await asyncio.to_thread(_db_get_url_sync, test_no)


async def db_upsert_url(test_no: str, url: str) -> None:
    async with _db_lock:
        await asyncio.to_thread(_db_upsert_url_sync, test_no, url)


# ---------------- report 폴더 캐시 ----------------
def _report_base_dir() -> str:
    return getattr(settings, "AGENT_REPORT_BASE_DIR", r"C:\Users\Administrator\report")


def _report_dir(test_no: str):
    import os
    import unicodedata
    from pathlib import Path
    return Path(os.path.join(_report_base_dir(), unicodedata.normalize("NFC", str(test_no))))


def _report_dir_has_files(test_no: str) -> bool:
    """report\\<시험번호> 폴더가 있고 파일이 1개 이상이면 True(=캐시 hit)."""
    import os
    folder = str(_report_dir(test_no))
    if not os.path.isdir(folder):
        return False
    for _root, _dirs, files in os.walk(folder):
        if files:
            return True
    return False


# ---------------- Worker orchestration ----------------
def _ensure_worker_thread() -> asyncio.AbstractEventLoop:
    """Playwright 전용 워커 스레드(ProactorEventLoop)를 1회만 기동하고 그 루프를 반환한다.
    ASGI(Selector) 루프와 분리된 이 루프에서만 브라우저/Playwright 작업을 수행한다."""
    global _worker_thread, _worker_loop_obj, _job_queue, _worker_task
    if _worker_loop_obj is not None:
        return _worker_loop_obj
    with _worker_start_lock:
        if _worker_loop_obj is not None:
            return _worker_loop_obj

        def _run() -> None:
            global _worker_loop_obj, _job_queue, _worker_task
            if sys.platform.startswith("win"):
                loop = asyncio.ProactorEventLoop()  # 서브프로세스(브라우저) 지원
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _worker_loop_obj = loop
            _job_queue = asyncio.Queue()
            _worker_task = loop.create_task(_worker_loop())
            logger_worker.info("worker_thread_started (Proactor=%s)", sys.platform.startswith("win"))
            _worker_ready.set()
            loop.run_forever()

        _worker_thread = threading.Thread(target=_run, name="playwright-worker", daemon=True)
        _worker_thread.start()
        if not _worker_ready.wait(timeout=15):
            raise RuntimeError("Playwright 워커 스레드 기동 실패(타임아웃)")
        return _worker_loop_obj


async def _submit_and_wait(cert_date: str, test_no: str, request_ip: str, action: str) -> Dict[str, Any]:
    """워커 루프에서 실행: 큐에 잡을 넣고(같은 루프의 Future) 결과를 기다린다."""
    assert _job_queue is not None
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    await _job_queue.put(
        {
            "cert_date": cert_date,
            "test_no": test_no,
            "request_ip": request_ip,
            "action": action,
            "future": fut,
        }
    )
    return await fut


async def enqueue_playwright_job(cert_date: str, test_no: str, request_ip: str, action: str = "url") -> Dict[str, Any]:
    """작업을 워커 스레드(Proactor 루프)에 넘기고 결과를 기다려 반환한다.

    ASGI(Selector) 루프 → 워커(Proactor) 루프로 run_coroutine_threadsafe 로 넘기고,
    반환된 concurrent.futures.Future 를 wrap_future 로 ASGI 루프에서 await 한다.
    """
    worker_loop = _ensure_worker_thread()
    queue_ahead = _job_queue.qsize() if _job_queue is not None else 0
    queue_position = queue_ahead + 1
    queue_total = queue_position

    cfut = asyncio.run_coroutine_threadsafe(
        _submit_and_wait(cert_date, test_no, request_ip, action), worker_loop
    )
    result = await asyncio.wrap_future(cfut)
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

            # 3) 실제 작업 실행 (action 에 따라 URL 복사 / 문서 다운로드 분기)
            action = job.get("action", "url")
            lock_timeout = getattr(settings, "ECM_AGENT_LOCK_TIMEOUT_SECONDS", 600)
            async with async_ecm_agent_lock(timeout_seconds=lock_timeout):
                if action == "document":
                    result = await asyncio.wait_for(
                        run_document_download_on_page(
                            ecm_page, cert_date, test_no, request_ip=request_ip,
                        ),
                        timeout=600,  # 파일 다운로드는 URL 복사보다 오래 걸림
                    )
                else:
                    result = await asyncio.wait_for(
                        run_playwright_task_on_page(
                            ecm_page, cert_date, test_no, request_ip=request_ip,
                        ),
                        timeout=120,
                    )

            if fut is not None and not fut.cancelled():
                fut.set_result(result)

        except Exception as e:
            if fut is not None and not fut.cancelled():
                fut.set_exception(e)

            # 실패 시 reset
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
        logger_ws.info("ws_connect ip=%s", self._client_ip())
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

    async def _handle_document_action(
        self, cert_date: str, test_no: str, request_ip: str, scope: str = "report"
    ) -> None:
        """'문서' 버튼: 인증위원회 트리에서 문서를 report\\<시험번호> 로 HTTP 직접 다운로드한 뒤
        ZIP 링크를 반환한다. scope='report'(기본)면 시험성적서 Word 만, 'all'이면 전체.

        기존 Playwright + pywinauto 팝업 방식을 대체한다(브라우저/에이전트/락 불필요).
        """
        from urllib.parse import quote

        from main.views.testing.history_download import (
            download_history_documents,
            report_cache_valid,
        )

        download_url = f"/history/report/{quote(test_no)}/download/"
        report_only = scope != "all"

        # 1) 캐시: 같은 범위로 이미 받아둔 폴더가 있으면 ECM 접속 없이 즉시 전달
        try:
            cached = await asyncio.to_thread(report_cache_valid, test_no, report_only)
        except Exception:
            cached = False
        if cached:
            await self._safe_send({"status": "processing", "message": "저장된 문서 확인 완료..."})
            await self._safe_send({"status": "success", "download_url": download_url, "source": "cache"})
            await self.close()
            return

        # 2) ECM HTTP 다운로드
        label = "시험성적서" if report_only else "전체 문서"
        await self._safe_send({"status": "processing", "message": f"ECM에서 {label}를 다운로드 중입니다..."})
        try:
            result = await asyncio.to_thread(
                download_history_documents, cert_date, test_no, report_only=report_only
            )
            await self._safe_send(
                {
                    "status": "success",
                    "download_url": download_url,
                    "source": "ecm",
                    "doc_count": result.get("doc_count", 0),
                }
            )
        except Exception as exc:
            await self._safe_send(
                {
                    "status": "error",
                    "message": f"{test_no}의 ECM 문서 다운로드를 실패하였습니다. 다시 요청해주세요.",
                    "detail": str(exc),
                }
            )
        finally:
            try:
                await self.close()
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

        # history/similar 둘 다 동일하게 보내는 전제(프로토콜 유지)
        if not cert_date or not test_no:
            await self._safe_send({"status": "error", "message": "인증일자/시험번호가 누락되었습니다."})
            await self.close()
            return

        action = (payload.get("action") or "url").strip()

        # === '문서' 버튼: 인증위원회 트리에서 HTTP 직접 다운로드 → ZIP 링크 반환 ===
        # scope='report'(기본)=시험성적서 Word 만, 'all'=전체 문서.
        if action == "document":
            scope = (payload.get("scope") or "report").strip().lower()
            await self._handle_document_action(cert_date, test_no, request_ip, scope=scope)
            return

        # 2) DB 캐시 먼저 조회 (hit면 ECM 접속/큐 없이 바로 success)
        try:
            cached = await db_get_url(test_no)
        except Exception:
            cached = None

        if cached:
            await self._safe_send({"status": "processing", "message": "DB 캐시에서 URL 조회 완료..."})
            await self._safe_send({"status": "success", "url": cached, "source": "cache"})
            await self.close()
            return

        # 3) enqueue 시점 큐 정보(대략) - 캐시 miss인 경우에만 의미 있음
        try:
            # 워커 스레드(Proactor 루프) 기동은 블로킹이므로 이벤트 루프를 막지 않게 to_thread
            await asyncio.to_thread(_ensure_worker_thread)
            queue_ahead = _job_queue.qsize() if _job_queue is not None else 0
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
            await self._safe_send({"status": "wait", "message": "ECM 작업 큐에 등록 중..."})

        # 4) 실행 안내(대기/실행 흐름)
        await self._safe_send({"status": "processing", "message": "ECM 작업 대기/실행 중..."})

        # 5) ECM 자동화 실행 → URL 반환 → DB 저장 → success
        try:
            pack = await enqueue_playwright_job(cert_date, test_no, request_ip=request_ip)
            result = (pack or {}).get("result") or {}
            url = (result.get("url") or "").strip()
            if not url:
                raise RuntimeError("URL 생성 실패")

            # DB 저장(실패해도 사용자 성공 흐름은 유지)
            try:
                await db_upsert_url(test_no, url)
            except Exception:
                pass

            await self._safe_send({"status": "success", "url": url, "source": "ecm"})

        except StepError as e:
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
