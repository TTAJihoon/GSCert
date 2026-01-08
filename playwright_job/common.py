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

TIMEOUTS = {
    "GOTO_MS": 10_000,
    "TREE_WAIT_MS": 5_000,
    "CLICK_MS": 3_000,
    "DOC_CLICK_MS": 3_000,   # 네가 합의한 3초
    "FILE_WAIT_MS": 5_000,
    "COPY_MS": 6_000,        # 복사/클립보드 반영은 조금 더 여유
}

# =========================
# Errors / Logging policy
# =========================

@dataclass
class StepError(Exception):
    step_no: int
    error_kind: str         # 한글 요약
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

def get_date_parts(cert_date: str) -> tuple[str, str]:
    """
    'yyyy.mm.dd' 또는 'yyyy-mm-dd' -> ('yyyy', 'yyyymmdd')
    """
    m = re.match(r"^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$", cert_date or "")
    if not m:
        raise ValueError(f"날짜 형식 오류: {cert_date}")
    y, mo, d = m.groups()
    return y, f"{y}{mo.zfill(2)}{d.zfill(2)}"


def testno_pat(test_no: str) -> Pattern:
    safe_no = re.escape(test_no).replace(r"\-", "[-_]")
    return re.compile(safe_no, re.IGNORECASE)
