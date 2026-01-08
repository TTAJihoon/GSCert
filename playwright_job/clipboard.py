# myproject/playwright_job/clipboard.py
from __future__ import annotations

import asyncio
from uuid import uuid4
from typing import Optional

try:
    import win32clipboard
    import win32con
except ImportError:
    win32clipboard = None
    win32con = None


def make_sentinel() -> str:
    return f"__ECM_SENTINEL__{uuid4().hex}"


def _require_pywin32() -> None:
    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32 미설치로 클립보드 사용 불가")


def _get_text_sync() -> str:
    _require_pywin32()
    text = ""
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    return text or ""


def _set_text_sync(text: str) -> None:
    _require_pywin32()
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


async def get_clipboard_text(retries: int = 10, delay_sec: float = 0.05) -> str:
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            return await asyncio.to_thread(_get_text_sync)
        except Exception as e:
            last = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 읽기 실패: {last}")


async def set_clipboard_text(text: str, retries: int = 10, delay_sec: float = 0.05) -> None:
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            await asyncio.to_thread(_set_text_sync, text)
            return
        except Exception as e:
            last = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 쓰기 실패: {last}")


async def wait_clipboard_not_equal(before: str, timeout_ms: int = 6000, interval_ms: int = 100) -> str:
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            cur = await get_clipboard_text()
        except Exception:
            cur = ""
        if cur and cur != before:
            return cur
        await asyncio.sleep(interval_ms / 1000.0)
        elapsed += interval_ms
    return ""
