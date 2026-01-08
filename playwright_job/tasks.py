# myproject/playwright_job/tasks.py
from __future__ import annotations

from typing import Dict

from playwright.async_api import Browser, Page

from .common import StepError, TIMEOUTS, log_start, log_done, screenshot_name, log_fail
from .ecm import run_ecm_flow


async def run_playwright_task_on_page(
    page: Page,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """
    정책:
      - START/DONE 최소 로그
      - step 실패 로그/스크린샷은 ecm.run_ecm_flow 내부에서 1줄로 남김
      - 여기서는 StepError 전달 + 예기치 못한 에러만 S99로 정리
    """
    log_start(request_ip)
    try:
        out = await run_ecm_flow(page, cert_date, test_no, request_ip=request_ip)
        log_done(request_ip)

        # 소비자/JS 호환을 위해 "url" 키 유지
        return {"url": out["file_url"]}

    except StepError:
        # step별 로그/스크린샷 이미 기록됨
        raise
    except Exception:
        # step 밖의 알 수 없는 오류
        shot = screenshot_name()
        try:
            await page.screenshot(path=shot)
        except Exception:
            shot = f"{shot}(FAILED)"
        log_fail(request_ip, 99, "알 수 없는 오류", shot)
        raise StepError(step_no=99, error_kind="알 수 없는 오류", screenshot=shot, request_ip=request_ip)


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
            pass
