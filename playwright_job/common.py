import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Pattern

logger = logging.getLogger("playwright_job")

@dataclass
class StepError(Exception):
    step_no: int
    error_kind: str
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

def log_fail(ip: str, step_no: int, kind: str, shot: str) -> None:
    logger.error("%s | %s | S%d | %s | %s", now_ts(), ip, step_no, kind, shot)

def get_date_parts(cert_date: str) -> tuple[str, str]:
    m = re.match(r"^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$", cert_date or "")
    if not m:
        raise ValueError(f"날짜 형식 오류: {cert_date}")
    y, mo, d = m.groups()
    return y, f"{y}{mo.zfill(2)}{d.zfill(2)}"

def testno_pat(test_no: str) -> Pattern:
    safe_no = re.escape(test_no).replace(r"\-", "[-_]")
    return re.compile(safe_no, re.IGNORECASE)
