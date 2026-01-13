# myproject/playwright_job/url_cache.py
import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Optional

from django.conf import settings

# DB: main/data/ecmURL.db
DB_PATH = Path(settings.BASE_DIR) / "main" / "data" / "ecmURL.db"

# 동시 접근 보호(프로세스 내)
_db_lock = asyncio.Lock()


def _ensure_dir_and_table_sync() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ecm_url (
                test_no TEXT PRIMARY KEY,
                url     TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _get_url_sync(test_no: str) -> Optional[str]:
    _ensure_dir_and_table_sync()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT url FROM ecm_url WHERE test_no = ?", (test_no,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _upsert_url_sync(test_no: str, url: str) -> None:
    _ensure_dir_and_table_sync()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ecm_url(test_no, url)
            VALUES(?, ?)
            ON CONFLICT(test_no) DO UPDATE SET url=excluded.url
            """,
            (test_no, url),
        )
        conn.commit()
    finally:
        conn.close()


async def get_cached_url(test_no: str) -> Optional[str]:
    """
    test_no로 캐시 조회(없으면 None)
    """
    if not test_no:
        return None

    async with _db_lock:
        return await asyncio.to_thread(_get_url_sync, test_no)


async def save_cached_url(test_no: str, url: str) -> None:
    """
    test_no-url upsert
    """
    if not test_no or not url:
        return

    async with _db_lock:
        await asyncio.to_thread(_upsert_url_sync, test_no, url)
