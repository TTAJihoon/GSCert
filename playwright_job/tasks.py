import logging
from dataclasses import dataclass
from typing import Dict, Optional

from playwright.async_api import Browser, Page

from .common import now_ts, screenshot_name, parse_cert_date, build_testno_pattern, TIMEOUTS
from .ecm import (
    goto_base,
    wait_left_tree,
    click_year,
    click_committee,
    click_date_folder,
    click_test_folder,
    click_document_in_list,
    wait_file_list,
    select_target_file_and_copy_url,
)

logger = logging.getLogger("playwright_job.task")


@dataclass
class StepError(Exception):
    step_no: int
    error_kind: str
    screenshot: str
    request_ip: str = "-"

    def __str__(self) -> str:
        return f"S{self.step_no} {self.error_kind} screenshot={self.screenshot} ip={self.request_ip}"


def _log_fail(request_ip: str, step_no: int, error_kind: str, screenshot: str) -> None:
    # 요구사항: 시간, 요청IP, step 번호, 오류 종류, 스크린샷만
    logger.error("%s | %s | S%d | %s | %s", now_ts(), request_ip, step_no, error_kind, screenshot)


async def _run_step(page: Page, step_no: int, error_kind: str, request_ip: str, coro) -> Dict:
    try:
        out = await coro
        return out or {}
    except StepError:
        raise
    except Exception:
        ss = screenshot_name()
        try:
            await page.screenshot(path=ss)
        except Exception:
            ss = f"{ss}(FAILED)"
        _log_fail(request_ip, step_no, error_kind, ss)
        raise StepError(step_no=step_no, error_kind=error_kind, screenshot=ss, request_ip=request_ip)


async def run_playwright_task_on_page(
    page: Page,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """
    ✅ step 분리 실행(네가 보는 step 번호 유지)
    """
    year, yyyymmdd = parse_cert_date(cert_date)
    test_no_pat = build_testno_pattern(test_no)

    await _run_step(page, 1, "페이지 이동 실패", request_ip, goto_base(page))
    await _run_step(page, 2, "좌측 트리 로딩 실패", request_ip, wait_left_tree(page))

    await _run_step(page, 3, "연도 폴더 클릭 실패", request_ip, click_year(page, year))
    await _run_step(page, 4, "위원회 폴더 클릭 실패", request_ip, click_committee(page))
    await _run_step(page, 5, "인증일자 폴더 클릭 실패", request_ip, click_date_folder(page, yyyymmdd))
    await _run_step(page, 6, "시험번호 폴더 클릭 실패", request_ip, click_test_folder(page, test_no))

    # ✅ 여기(문서 클릭) 실패가 가장 많아서 로딩 대기 로직을 ecm.py에서 wait_for 기반으로 수정함
    await _run_step(page, 7, "문서 목록에서 대상 문서 클릭 실패", request_ip, click_document_in_list(page, test_no_pat))

    await _run_step(page, 8, "파일 목록 로딩 실패", request_ip, wait_file_list(page))

    out = await _run_step(page, 9, "URL 복사 실패", request_ip, select_target_file_and_copy_url(page, test_no_pat))

    url = out.get("url")
    if not url:
        # 이건 논리상 거의 없지만, step 번호 유지 위해 99 처리
        ss = screenshot_name()
        try:
            await page.screenshot(path=ss)
        except Exception:
            ss = f"{ss}(FAILED)"
        _log_fail(request_ip, 99, "URL 생성 실패", ss)
        raise StepError(step_no=99, error_kind="URL 생성 실패", screenshot=ss, request_ip=request_ip)

    return {"url": url}


async def run_playwright_task(
    browser: Browser,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """
    (선택) 새 context/page를 매번 만들어 돌리고 싶을 때
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
