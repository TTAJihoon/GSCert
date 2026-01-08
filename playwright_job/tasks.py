import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Pattern

from playwright.async_api import Browser, Page

# Windows clipboard
try:
    import win32clipboard
    import win32con
except ImportError:
    win32clipboard = None
    win32con = None

logger = logging.getLogger("playwright_job.task")

ECM_BASE_URL = "http://210.104.181.10"

# ======= StepError (traceback 없이 간단히) =======

@dataclass
class StepError(Exception):
    step_no: int
    error_kind: str         # 한글 요약
    screenshot: str
    request_ip: str = "-"
    def __str__(self) -> str:
        return f"S{self.step_no} {self.error_kind} screenshot={self.screenshot} ip={self.request_ip}"


# ======= 유틸 =======

def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _screenshot_name(prefix: str = "playwright_error") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

def _get_date_parts(cert_date: str) -> tuple[str, str]:
    """
    'yyyy.mm.dd' 또는 'yyyy-mm-dd' -> ('yyyy', 'yyyymmdd')
    """
    m = re.match(r"^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$", cert_date or "")
    if not m:
        raise ValueError(f"날짜 형식 오류: {cert_date}")
    y, mo, d = m.groups()
    return y, f"{y}{mo.zfill(2)}{d.zfill(2)}"

def _testno_pat(test_no: str) -> Pattern:
    safe_no = re.escape(test_no).replace(r"\-", "[-_]")
    return re.compile(safe_no, re.IGNORECASE)

def _log_start(request_ip: str) -> None:
    logger.info("%s | %s | START", _now_ts(), request_ip)

def _log_done(request_ip: str) -> None:
    logger.info("%s | %s | DONE", _now_ts(), request_ip)

def _log_fail(request_ip: str, step_no: int, error_kind: str, screenshot: str) -> None:
    # 요구사항: 시간, 요청IP, step, 오류종류, 스크린샷만
    logger.error("%s | %s | S%d | %s | %s", _now_ts(), request_ip, step_no, error_kind, screenshot)


# ======= Clipboard =======

def _get_clipboard_text_sync() -> str:
    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32 미설치로 클립보드 사용 불가")
    text = ""
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    return text or ""

async def _get_clipboard_text(retries: int = 5, delay_sec: float = 0.05) -> str:
    last_exc: Optional[Exception] = None
    for _ in range(retries):
        try:
            return await asyncio.to_thread(_get_clipboard_text_sync)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 읽기 실패: {last_exc}")

async def _wait_clipboard_change(before: str, timeout_ms: int = 5000, interval_ms: int = 100) -> str:
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            current = await _get_clipboard_text()
        except Exception:
            current = ""
        if current and current != before:
            return current
        await asyncio.sleep(interval_ms / 1000.0)
        elapsed += interval_ms
    return ""


# ======= DOM Selectors (네가 준 HTML 기반) =======

DOC_ROOT = "#main-list-document"
DOC_TABLE = f"{DOC_ROOT} table.document-list-table"
DOC_ROW_ALL = f"{DOC_ROOT} tr.document-list-item"
DOC_CLICK_SPAN_IN_ROW = 'span[events="document-list-viewDocument-click"]'

LEFT_PANEL_MENU = "#edm-left-panel-menu"
FOLDER_PANEL_ACTIVE = (
    'div.edm-left-panel-menu-sub-item[submenu_type="Folder"].ui-accordion-content-active'
)
FOLDER_TREE = "#edm-folder"   # jstree container

FILE_ROW = "tr.prop-view-file-list-item"
URL_COPY_BTN = "div#prop-view-document-btn-url-copy"


def _css_attr_eq(attr: str, value: str) -> str:
    v = (value or "").replace('"', '\\"')
    return f'[{attr}="{v}"]'


# ======= Step Runner =======

async def _run_step(
    page: Page,
    step_no: int,
    error_kind: str,
    request_ip: str,
    coro,
) -> Dict:
    """
    성공하면 coro 결과 dict 반환.
    실패하면 screenshot 찍고 StepError로 변환 (traceback 로그 X)
    """
    try:
        out = await coro
        return out or {}
    except StepError:
        raise
    except Exception:
        screenshot = _screenshot_name()
        try:
            await page.screenshot(path=screenshot)
        except Exception:
            # 스크린샷 실패해도 로그 포맷은 유지
            screenshot = f"{screenshot}(FAILED)"
        _log_fail(request_ip, step_no, error_kind, screenshot)
        raise StepError(step_no=step_no, error_kind=error_kind, screenshot=screenshot, request_ip=request_ip)


# ======= Step Implementations =======

async def _s1_goto(page: Page, timeout_ms: int) -> Dict:
    resp = await page.goto(ECM_BASE_URL, timeout=timeout_ms, wait_until="domcontentloaded")
    if resp is None:
        raise RuntimeError("응답 없음")
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status}")
    return {"status": resp.status}

async def _s2_wait_left_tree(page: Page, timeout_ms: int) -> Dict:
    # 좌측 패널이 표시되었는지 (display/visibility 기준은 Playwright가 판단)
    await page.locator(LEFT_PANEL_MENU).wait_for(state="visible", timeout=timeout_ms)
    # Folder 패널이 active 상태인지(트리 영역)
    await page.locator(FOLDER_PANEL_ACTIVE).wait_for(state="visible", timeout=timeout_ms)
    await page.locator(FOLDER_TREE).wait_for(state="visible", timeout=timeout_ms)
    return {}

async def _click_tree_text(page: Page, text: str, timeout_ms: int) -> None:
    # 트리 클릭은 #edm-folder 범위로 제한 (오탐 방지)
    tree = page.locator(FOLDER_TREE)
    await tree.get_by_text(text).first.click(timeout=timeout_ms)

async def _s3_click_year(page: Page, year: str, timeout_ms: int) -> Dict:
    # 보통 "2025 시험서비스" 형태이므로 우선 그걸로 시도하고, 실패하면 year만
    try:
        await _click_tree_text(page, f"{year} 시험서비스", timeout_ms)
    except Exception:
        await _click_tree_text(page, year, timeout_ms)
    return {}

async def _s4_click_committee(page: Page, timeout_ms: int) -> Dict:
    await _click_tree_text(page, "GS인증심의위원회", timeout_ms)
    return {}

async def _s5_click_date(page: Page, date_str: str, timeout_ms: int) -> Dict:
    # date_str(yyyymmdd)가 포함된 노드를 클릭
    await _click_tree_text(page, date_str, timeout_ms)
    return {}

async def _s6_click_testno(page: Page, test_no: str, timeout_ms: int) -> Dict:
    # "가. GS-A-25-0173" 같은 형태라 test_no 포함 텍스트 클릭
    await _click_tree_text(page, test_no, timeout_ms)
    return {}

async def _s7_wait_and_click_document(page: Page, test_no: str, timeout_ms: int) -> Dict:
    # 문서 테이블이 보일 때까지
    await page.locator(DOC_TABLE).wait_for(state="visible", timeout=timeout_ms)

    # 1) 가장 안정: '클릭 스팬(events="document-list-viewDocument-click")' 텍스트에 시험번호가 포함된 것
    #    예: "자. GS-A-25-0159" -> test_no 포함이므로 매칭됨
    import re
    pat = re.compile(re.escape(test_no), re.IGNORECASE)

    span = page.locator(DOC_CLICK_SPAN_IN_ROW).filter(has_text=pat).first

    # 스팬이 뜰 때까지 기다렸다가 클릭
    await span.wait_for(state="visible", timeout=timeout_ms)
    await span.click(timeout=timeout_ms)
    return {}

async def _s8_wait_file_list(page: Page, timeout_ms: int) -> Dict:
    # 파일 목록 row가 "1개 이상"이면 정상(네 조건)
    rows = page.locator(FILE_ROW)
    await rows.first.wait_for(state="visible", timeout=timeout_ms)
    cnt = await rows.count()
    if cnt < 1:
        raise RuntimeError("파일 목록 0건")
    return {"file_count": cnt}

async def _s9_select_target_file_and_copy(page: Page, test_no_pat: Pattern, timeout_ms: int) -> Dict:
    # 파일 row에서 시험성적서 + 시험번호 매칭 1개를 선택
    rows = page.locator(FILE_ROW)
    target = rows.filter(has_text=test_no_pat).filter(has_text="시험성적서")

    cnt = await target.count()
    if cnt != 1:
        raise RuntimeError(f"시험성적서 파일 row 확정 실패(count={cnt})")

    checkbox = target.first.locator('input[type="checkbox"]')
    await checkbox.check(timeout=timeout_ms)

    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32 미설치로 URL 복사 불가")

    before = ""
    try:
        before = await _get_clipboard_text()
    except Exception:
        before = ""

    btn = page.locator(URL_COPY_BTN).first
    await btn.wait_for(state="visible", timeout=timeout_ms)
    await btn.click(timeout=timeout_ms)

    pasted = await _wait_clipboard_change(before, timeout_ms=timeout_ms)
    if not pasted:
        raise RuntimeError("클립보드 변화 없음")

    first_line = pasted.splitlines()[0]
    m = re.search(r"(https?://\S+)", first_line)
    if not m:
        raise RuntimeError("URL 파싱 실패")
    return {"url": m.group(1)}


# ======= Main Task =======

async def run_playwright_task_on_page(
    page: Page,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """
    요구 로그 정책:
      - START / DONE 은 최소로
      - 실패 시: 시간|IP|S#|오류종류(한글)|스크린샷 1줄
      - traceback 출력 금지 (logger.exception 금지)
    """
    _log_start(request_ip)

    year, date_str = _get_date_parts(cert_date)
    test_no_pat = _testno_pat(test_no)

    # timeouts
    TO_GOTO = 10_000
    TO_TREE = 5_000
    TO_CLICK = 3_000
    TO_DOC = 3_000     # 너가 합의한 3초
    TO_FILE = 5_000
    TO_COPY = 5_000

    try:
        await _run_step(page, 1, "페이지 이동 실패", request_ip, _s1_goto(page, TO_GOTO))
        await _run_step(page, 2, "좌측 트리 로딩 실패", request_ip, _s2_wait_left_tree(page, TO_TREE))

        await _run_step(page, 3, "연도 폴더 클릭 실패", request_ip, _s3_click_year(page, year, TO_CLICK))
        await _run_step(page, 4, "위원회 폴더 클릭 실패", request_ip, _s4_click_committee(page, TO_CLICK))
        await _run_step(page, 5, "인증일자 폴더 클릭 실패", request_ip, _s5_click_date(page, date_str, TO_CLICK))
        await _run_step(page, 6, "시험번호 폴더 클릭 실패", request_ip, _s6_click_testno(page, test_no, TO_CLICK))

        await _run_step(page, 7, "문서 목록에서 대상 문서 클릭 실패", request_ip, _s7_wait_and_click_document(page, test_no, TO_DOC))

        await _run_step(page, 8, "파일 목록 로딩 실패", request_ip, _s8_wait_file_list(page, TO_FILE))

        out = await _run_step(page, 9, "URL 복사 실패", request_ip, _s9_select_target_file_and_copy(page, test_no_pat, TO_COPY))

        _log_done(request_ip)
        return {"url": out["url"]}

    except StepError:
        # StepError는 이미 한 줄 로그가 남았고, traceback 없이 상위로 전달
        raise
    except Exception:
        # StepError 외 예외도 동일 정책 적용
        screenshot = _screenshot_name()
        try:
            await page.screenshot(path=screenshot)
        except Exception:
            screenshot = f"{screenshot}(FAILED)"
        _log_fail(request_ip, 99, "알 수 없는 오류", screenshot)
        raise StepError(step_no=99, error_kind="알 수 없는 오류", screenshot=screenshot, request_ip=request_ip)


async def run_playwright_task(
    browser: Browser,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """
    래퍼: 새 context/page 생성 후 작업 실행
    """
    context = await browser.new_context()
    page = await context.new_page()
    try:
        return await run_playwright_task_on_page(page, cert_date, test_no, request_ip=request_ip)
    finally:
        try:
            await context.close()
        except Exception:
            # 여기서도 traceback 로그 금지
            pass
