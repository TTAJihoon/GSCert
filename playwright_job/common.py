# myproject/playwright_job/common.py
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Pattern

logger = logging.getLogger("playwright_job")


# =========================
# Config / Timeouts
# =========================

ECM_BASE_URL = "http://210.104.181.10"


@dataclass(frozen=True)
class Timeouts:
    # page
    GOTO: int = 10_000

    # left tree
    LEFT_TREE: int = 5_000
    CLICK_TREE: int = 3_000

    # document/file
    DOC_CLICK: int = 3_000          # 합의: 3초
    FILE_LIST: int = 5_000
    COPY_URL: int = 6_000           # 클립보드 반영 여유

    # worker wrapper
    GET_BROWSER: int = 30
    JOB_TOTAL: int = 120


TIMEOUTS = Timeouts()


# =========================
# Errors / Logging policy
# =========================

@dataclass
class StepError(Exception):
    step_no: int
    error_kind: str     # 한글 요약
    screenshot: str
    request_ip: str = "-"

    def __str__(self) -> str:
        return f"S{self.step_no} {self.error_kind} screenshot={self.screenshot} ip={self.request_ip}"


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def screenshot_name(prefix: str = "playwright_error") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"


def log_start(ip: str) -> None:
    logger.info("%s | %s | START", now_ts(), ip)


def log_done(ip: str) -> None:
    logger.info("%s | %s | DONE", now_ts(), ip)


def log_fail(ip: str, step_no: int, error_kind: str, screenshot: str) -> None:
    # 요구사항: 시간, 요청IP, step 번호, 오류 종류, 스크린샷만
    logger.error("%s | %s | S%d | %s | %s", now_ts(), ip, step_no, error_kind, screenshot)


# =========================
# Parsing utils
# =========================

def parse_cert_date(cert_date: str) -> tuple[str, str]:
    """
    'yyyy.mm.dd' 또는 'yyyy-mm-dd' -> ('yyyy', 'yyyymmdd')
    """
    m = re.match(r"^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$", cert_date or "")
    if not m:
        raise ValueError(f"날짜 형식 오류: {cert_date}")
    y, mo, d = m.groups()
    return y, f"{y}{mo.zfill(2)}{d.zfill(2)}"


def compile_testno_pat(test_no: str) -> Pattern[str]:
    # 임의 폴백(하이픈/언더스코어 혼용 등) 추가하지 않음.
    return re.compile(re.escape(test_no), re.IGNORECASE)
