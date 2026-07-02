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


async def run_document_download_on_page(
    page: Page,
    cert_date: str,
    test_no: str,
    request_ip: str = "-",
) -> Dict[str, str]:
    """'문서' 버튼용: S1~S6(기존 탐색) → 문서 전체선택+파일다운로드 → report\\<시험번호>
    폴더로 다운로드. 다운로드된 폴더 경로를 반환한다(브라우저 전달은 컨슈머가 처리).

    S7~S8 의 전체선택/다운로드 트리거와 폴더 팝업 처리는 ECM 산출물 점검용 검증 코드를
    재사용한다(main.views.review.ecm_download / ecm_agent_popup).
    """
    import asyncio
    import os
    import unicodedata

    from django.conf import settings
    from main.views.review.ecm_download import select_all_documents, click_download_menu
    from main.views.review.ecm_agent_popup import handle_folder_popup_and_download

    year, yyyymmdd = parse_cert_date(cert_date)

    # S1~S6: 기존 인증일자 경로 탐색(시험번호 폴더까지)
    await _run_step(page, 1, "페이지 이동 실패", request_ip, goto_base(page))
    await _run_step(page, 2, "좌측 트리 로딩 실패", request_ip, wait_left_tree(page))
    await _run_step(page, 3, "연도 폴더 클릭 실패", request_ip, click_year(page, year))
    await _run_step(page, 4, "위원회 폴더 클릭 실패", request_ip, click_committee(page))
    await _run_step(page, 5, "인증일자 폴더 클릭 실패", request_ip, click_date_folder(page, yyyymmdd))
    await _run_step(page, 6, "시험번호 폴더 클릭 실패", request_ip, click_test_folder(page, test_no))

    report_base = getattr(settings, "AGENT_REPORT_BASE_DIR", r"C:\Users\Administrator\report")
    folder_name = unicodedata.normalize("NFC", str(test_no))

    # S7: 문서 목록 전체 선택
    try:
        count = await select_all_documents(page)
    except StepError:
        raise
    except Exception:
        raise await _step_error(page, 7, "문서 전체 선택 실패", request_ip)
    if not count:
        raise await _step_error(page, 7, "다운로드할 문서가 없습니다", request_ip)

    # S7: '파일 다운로드' 메뉴 클릭 → 다운로드 폴더 팝업 발생
    await _run_step(page, 7, "파일 다운로드 메뉴 클릭 실패", request_ip, click_download_menu(page))

    # S8: 폴더 찾아보기 팝업 처리 → report\<시험번호> 에 생성/다운로드/대기 (동기 → 스레드)
    popup = await asyncio.to_thread(
        handle_folder_popup_and_download, folder_name, "", 2, [], "", report_base
    )
    if not getattr(popup, "success", False):
        raise await _step_error(
            page, 8, getattr(popup, "error_message", None) or "다운로드 팝업 처리 실패", request_ip
        )

    download_dir = getattr(popup, "target_dir", "") or os.path.join(report_base, folder_name)
    return {"download_dir": download_dir, "test_no": folder_name, "doc_count": str(count)}


async def _step_error(page: Page, step_no: int, error_kind: str, request_ip: str) -> StepError:
    ss = screenshot_name()
    try:
        await page.screenshot(path=ss)
    except Exception:
        ss = f"{ss}(FAILED)"
    _log_fail(request_ip, step_no, error_kind, ss)
    return StepError(step_no=step_no, error_kind=error_kind, screenshot=ss, request_ip=request_ip)


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
