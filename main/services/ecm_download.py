"""
ECM 웹페이지1 파일 다운로드 자동화 (5~8단계).

프로젝트 폴더 선택 -> 문서 전체 선택 -> 파일 다운로드 메뉴 클릭
-> 폴더 선택 팝업 처리 -> 전송현황 대기까지 수행한다.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from playwright.async_api import Browser, Page, async_playwright

from .ecm_selectors import (
    ADVANCED_MENU_BTN,
    CONTEXT_MENU,
    DOC_ROWS,
    DOC_TABLE,
    DOWNLOAD_MENU_FALLBACK,
    DOWNLOAD_MENU_ITEM,
    FOLDER_PANEL_ACTIVE,
    FOLDER_TREE,
    LEFT_PANEL_MENU,
    SELECT_ALL_CHECKBOX,
    SPLASHSCREEN,
)

logger = logging.getLogger("main.services.ecm_download")


def _timeouts():
    return getattr(settings, "ECM_DOWNLOAD_TIMEOUTS", {
        "GOTO": 15_000,
        "FOLDER_SEARCH": 10_000,
        "DOC_LIST": 10_000,
        "MENU_VISIBLE": 5_000,
        "SPLASH": 10_000,
    })


def _ecm_url():
    return getattr(settings, "ECM_BASE_URL", "http://210.96.71.85")


# --- ECM 트리 경로 설정 ---
# 실제 구조: 상암AX센터(초기 펼침) > {연도}년 시험서비스 > 01 GS인증시험(1등급) > 프로젝트 폴더
ECM_TREE_ROOT = "상암AX센터"
ECM_TREE_TEST_TYPE = "01 GS인증시험(1등급)"


@dataclass
class DownloadStepResult:
    success: bool
    doc_count: int = 0
    error_step: str = ""
    error_message: str = ""


async def _wait_splash_done(page: Page) -> None:
    t = _timeouts()
    await page.locator(SPLASHSCREEN).wait_for(state="hidden", timeout=t["SPLASH"])


async def open_ecm_page(browser: Browser) -> Page:
    """ECM 접속 후 좌측 트리가 보일 때까지 대기한다."""
    context = await browser.new_context(accept_downloads=True)
    page = await context.new_page()
    t = _timeouts()
    resp = await page.goto(_ecm_url(), timeout=t["GOTO"], wait_until="domcontentloaded")
    if resp is None or resp.status >= 400:
        status = resp.status if resp else "no response"
        raise RuntimeError(f"ECM 접속 실패: HTTP {status}")
    await _wait_splash_done(page)
    await page.locator(LEFT_PANEL_MENU).wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    await page.locator(FOLDER_PANEL_ACTIVE).wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    await page.locator(FOLDER_TREE).wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    return page


async def navigate_to_project_folder(page: Page, project_number: str) -> None:
    """ECM 트리에서 상위 폴더를 순서대로 펼치고 프로젝트 폴더를 클릭한다.

    트리 경로:
      상암AX센터(초기 펼침) > {연도}년 시험서비스 > 01 GS인증시험(1등급) > 프로젝트 폴더
    """
    t = _timeouts()
    tree = page.locator(FOLDER_TREE)

    # 프로젝트번호에서 연도 추출: TTA-26-00009 → 2026
    m = re.match(r"TTA-(\d{2})-", project_number)
    if not m:
        raise RuntimeError(f"프로젝트번호 형식 오류: {project_number}")
    year = f"20{m.group(1)}"

    # Step 1: 연도 시험서비스 폴더 클릭 (예: "2026년 시험서비스")
    year_folder = tree.locator("a", has_text=re.compile(f"^{year}.*시험서비스"))
    try:
        await year_folder.first.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    except Exception:
        # 상암AX센터가 접혀있을 수 있음 → 클릭해서 확장
        ax_node = tree.locator("a", has_text=ECM_TREE_ROOT).first
        await ax_node.click(timeout=3000)
        await _wait_splash_done(page)
        await year_folder.first.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])

    await year_folder.first.click()
    await _wait_splash_done(page)

    # Step 2: 01 GS인증시험(1등급) 폴더 클릭
    test_type_folder = tree.locator("a", has_text=ECM_TREE_TEST_TYPE).first
    await test_type_folder.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    await test_type_folder.click()
    await _wait_splash_done(page)

    # Step 3: 프로젝트번호를 포함하는 폴더 클릭
    project_folder = tree.locator("a", has_text=project_number).first
    await project_folder.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    await project_folder.click()
    await _wait_splash_done(page)


async def select_all_documents(page: Page) -> int:
    """문서 목록이 로딩되면 전체 선택 체크박스를 클릭하고 문서 수를 반환한다."""
    t = _timeouts()
    await page.locator(DOC_TABLE).wait_for(state="visible", timeout=t["DOC_LIST"])

    rows = page.locator(DOC_ROWS)
    try:
        await rows.first.wait_for(state="visible", timeout=t["DOC_LIST"])
    except Exception:
        return 0

    count = await rows.count()
    if count == 0:
        return 0

    checkbox = page.locator(SELECT_ALL_CHECKBOX)
    await checkbox.click(timeout=3000)
    return count


async def click_download_menu(page: Page) -> None:
    """고급 메뉴 → 파일 다운로드 항목을 클릭한다."""
    t = _timeouts()

    btn = page.locator(ADVANCED_MENU_BTN)
    await btn.click(timeout=3000)

    menu = page.locator(CONTEXT_MENU)
    await menu.wait_for(state="visible", timeout=t["MENU_VISIBLE"])

    item = page.locator(DOWNLOAD_MENU_ITEM)
    try:
        await item.wait_for(state="visible", timeout=3000)
        await item.click(timeout=3000)
    except Exception:
        logger.warning("menuevent selector 실패, fallback selector 사용")
        fallback = page.locator(DOWNLOAD_MENU_FALLBACK)
        await fallback.click(timeout=3000)


async def run_ecm_automation(browser: Browser, project_number: str) -> DownloadStepResult:
    """ECM 접속 → 프로젝트 폴더 선택 → 전체 선택 → 다운로드 메뉴 클릭.

    성공하면 Windows '폴더 찾아보기' 팝업이 표시된 상태로 반환한다.
    page는 caller가 닫아야 한다 (팝업 처리 후).
    """
    page: Optional[Page] = None
    try:
        page = await open_ecm_page(browser)
        await navigate_to_project_folder(page, project_number)

        doc_count = await select_all_documents(page)
        if doc_count == 0:
            if page:
                try:
                    ctx = page.context
                    await page.close()
                    await ctx.close()
                except Exception:
                    pass
            return DownloadStepResult(
                success=False,
                doc_count=0,
                error_step="문서 목록 확인",
                error_message=f"{project_number} 프로젝트의 문서 목록이 비어 있습니다.",
            )

        await click_download_menu(page)
        return DownloadStepResult(success=True, doc_count=doc_count)

    except Exception as exc:
        logger.exception("ECM 다운로드 자동화 실패: %s", project_number)
        if page:
            try:
                ctx = page.context
                await page.close()
                await ctx.close()
            except Exception:
                pass
        return DownloadStepResult(
            success=False,
            error_step="ECM 자동화",
            error_message=str(exc),
        )


async def launch_browser(*, headless: bool = True) -> Browser:
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless)
    return browser


async def close_browser(browser: Browser) -> None:
    try:
        await browser.close()
    except Exception:
        pass
