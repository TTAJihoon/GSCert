import asyncio
import uuid
from typing import Optional

try:
    import win32clipboard
    import win32con
except ImportError:
    win32clipboard = None
    win32con = None


def _require_pywin32():
    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32 미설치로 클립보드 사용 불가")


def get_clipboard_text_sync() -> str:
    _require_pywin32()
    text = ""
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    return text or ""


def set_clipboard_text_sync(text: str) -> None:
    _require_pywin32()
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


async def get_clipboard_text(retries: int = 5, delay_sec: float = 0.05) -> str:
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            return await asyncio.to_thread(get_clipboard_text_sync)
        except Exception as e:
            last = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 읽기 실패: {last}")


async def set_clipboard_text(text: str) -> None:
    await asyncio.to_thread(set_clipboard_text_sync, text)


async def wait_clipboard_not_equal(
    sentinel: str,
    timeout_ms: int = 6000,
    interval_ms: int = 100,
) -> str:
    """
    clipboard가 sentinel이 아닌 값으로 바뀌면 그 값을 반환.
    (이전 내용과 동일하더라도 sentinel로 먼저 덮어쓰면 '변화'가 발생하므로 안정적)
    """
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            cur = await get_clipboard_text()
        except Exception:
            cur = ""
        if cur and cur != sentinel:
            return cur
        await asyncio.sleep(interval_ms / 1000.0)
        elapsed += interval_ms
    return ""


def make_sentinel(prefix: str = "ECM_SENTINEL") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
