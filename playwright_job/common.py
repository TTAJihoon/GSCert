import asyncio
import re
from datetime import datetime
from typing import Optional, Pattern, Tuple

# Windows clipboard
try:
    import win32clipboard
    import win32con
except ImportError:
    win32clipboard = None
    win32con = None


ECM_BASE_URL = "http://210.104.181.10"

# ✅ timeout 정책:
# - DOC_CLICK은 “클릭 동작 자체” timeout(3초)
# - DOC_LIST는 “문서 목록이 화면에 나타날 때까지” 대기(좀 더 길게)
TIMEOUTS = {
    "GOTO": 10_000,
    "LEFT_TREE": 5_000,
    "TREE_CLICK": 3_000,

    "DOC_LIST": 10_000,   # 문서 row가 나타날 때까지
    "DOC_CLICK": 3_000,   # 클릭 수행 자체

    "FILE_LIST": 5_000,
    "COPY_WAIT": 5_000,
    "SPLASH": 10_000,
}


# ---------------- basic utils ----------------

def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def screenshot_name(prefix: str = "playwright_error") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

def parse_cert_date(cert_date: str) -> Tuple[str, str]:
    """
    'yyyy.mm.dd' or 'yyyy-mm-dd' -> (year, yyyymmdd)
    """
    m = re.match(r"^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$", cert_date or "")
    if not m:
        raise ValueError(f"날짜 형식 오류: {cert_date}")
    y, mo, d = m.groups()
    return y, f"{y}{mo.zfill(2)}{d.zfill(2)}"

def build_testno_pattern(test_no: str) -> Pattern:
    safe = re.escape(test_no).replace(r"\-", "[-_]")
    return re.compile(safe, re.IGNORECASE)


# ---------------- clipboard ----------------

def _clipboard_get_text_sync() -> str:
    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32 미설치로 클립보드 사용 불가")
    txt = ""
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            txt = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    return txt or ""

def _clipboard_set_text_sync(text: str) -> None:
    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32 미설치로 클립보드 사용 불가")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text or "")
    finally:
        win32clipboard.CloseClipboard()

async def clipboard_get_text(retries: int = 5, delay_sec: float = 0.05) -> str:
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            return await asyncio.to_thread(_clipboard_get_text_sync)
        except Exception as e:
            last = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 읽기 실패: {last}")

async def clipboard_set_text(text: str, retries: int = 5, delay_sec: float = 0.05) -> None:
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            await asyncio.to_thread(_clipboard_set_text_sync, text)
            return
        except Exception as e:
            last = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 쓰기 실패: {last}")

async def wait_clipboard_nonempty(timeout_ms: int, interval_ms: int = 100) -> str:
    """
    ✅ '같은 내용이 복사되어도 실패하지 않게' 만들기 위해:
    - 호출 전에 clipboard를 ""로 비우고 시작하면 됨
    - 여기서는 non-empty가 되는 순간 return
    """
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            cur = await clipboard_get_text()
        except Exception:
            cur = ""
        if cur.strip():
            return cur
        await asyncio.sleep(interval_ms / 1000.0)
        elapsed += interval_ms
    return ""
