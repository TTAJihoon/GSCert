from typing import Dict
from playwright.async_api import Page

from .common import StepError, screenshot_name, log_fail, get_date_parts, testno_pat

ECM_BASE_URL = "http://210.104.181.10"

async def get_file_url_from_ecm(
    page: Page,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """
    ECM UI 자동화만 담당.
    return: {"file_url": "...", "filename_hint": "..."}  # hint는 optional
    """
    year, date_str = get_date_parts(cert_date)
    pat = testno_pat(test_no)

    try:
        # TODO: 여기서 네 _s1~_s9를 그대로 옮기면 됨.
        # - goto
        # - left tree wait
        # - year/committee/date/test folder click
        # - doc row click
        # - file list wait
        # - "시험성적서" row 선택
        # - URL 확보(클립보드)
        file_url = "..."  # <- S9 결과
        filename_hint = f"{date_str}_{test_no}_시험성적서.docx"
        return {"file_url": file_url, "filename_hint": filename_hint}

    except StepError:
        raise
    except Exception:
        shot = screenshot_name()
        try:
            await page.screenshot(path=shot)
        except Exception:
            shot = f"{shot}(FAILED)"
        log_fail(request_ip, 99, "ECM 자동화 실패", shot)
        raise StepError(99, "ECM 자동화 실패", shot, request_ip=request_ip)
