"""
ECM 웹페이지1 파일 다운로드 자동화 (5~8단계).

프로젝트 폴더 선택 -> 문서 전체 선택 -> 파일 다운로드 메뉴 클릭
-> 폴더 선택 팝업 처리 -> 전송현황 대기까지 수행한다.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from django.conf import settings

try:
    from playwright.async_api import Browser, Page, async_playwright
except ImportError:
    Browser = Any
    Page = Any
    async_playwright = None

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

logger = logging.getLogger("main.views.review.ecm_download")
_PLAYWRIGHT_BY_BROWSER_ID = {}
LOCAL_NETWORK_DISABLE_FEATURES = (
    "LocalNetworkAccessChecks",
    "BlockInsecurePrivateNetworkRequests",
    "PrivateNetworkAccessSendPreflights",
    "PrivateNetworkAccessRespectPreflightResults",
)


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


def _browser_channel():
    return getattr(settings, "ECM_BROWSER_CHANNEL", "") or None


def _browser_args():
    args = getattr(settings, "ECM_BROWSER_ARGS", None)
    if args is None:
        return [
            f"--disable-features={','.join(LOCAL_NETWORK_DISABLE_FEATURES)}",
            "--disable-local-network-access-check",
        ]
    if isinstance(args, str):
        return [arg for arg in args.split() if arg]
    return list(args)


def _tree_root_index():
    return int(getattr(settings, "ECM_TREE_ROOT_INDEX", 1))


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
    page: Any = None


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
    try:
        await page.locator(LEFT_PANEL_MENU).wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
        await page.locator(FOLDER_PANEL_ACTIVE).wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
        await page.locator(FOLDER_TREE).wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
    except Exception as exc:
        detail = await _describe_unready_ecm_page(page)
        raise RuntimeError(detail) from exc
    return page


async def _describe_unready_ecm_page(page: Page) -> str:
    if page.is_closed():
        return "ECM 접속 후 화면이 자동으로 닫혔습니다. DestinyECM client 설치/로그인 상태를 확인하세요."

    title = ""
    body_text = ""
    screenshot_path = ""
    try:
        title = await page.title()
    except Exception:
        title = ""
    try:
        body_text = (await page.locator("body").inner_text(timeout=1000)).strip()
    except Exception:
        body_text = ""
    try:
        screenshot_path = await _save_debug_screenshot(page, prefix="ecm_unready")
    except Exception:
        logger.debug("ECM debug screenshot save failed", exc_info=True)

    hint = "ECM 좌측 폴더 트리를 찾지 못했습니다."
    haystack = f"{title}\n{body_text}"
    if "Smart Updater" in haystack or "SmartUpdater" in haystack or "접속 계정" in haystack:
        hint = (
            "DestinyECM Smart Updater 설치/계정 입력 화면입니다. "
            "ECM agent 상태와 Chrome local-network-access-check 비활성화 적용 여부를 확인하세요."
        )

    parts = [
        hint,
        f"url={page.url}",
    ]
    if title:
        parts.append(f"title={title}")
    if screenshot_path:
        parts.append(f"debug_screenshot={screenshot_path}")
    return " | ".join(parts)


async def _save_debug_screenshot(page: Page, *, prefix: str) -> str:
    base_dir = Path(getattr(settings, "BASE_DIR", "."))
    debug_dir = base_dir / "run" / "ecm_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = debug_dir / f"{prefix}_{stamp}.png"
    await page.screenshot(path=str(path), full_page=True)
    return str(path)


async def _save_debug_html(locator, *, prefix: str) -> str:
    base_dir = Path(getattr(settings, "BASE_DIR", "."))
    debug_dir = base_dir / "run" / "ecm_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = debug_dir / f"{prefix}_{stamp}.html"
    html = await locator.evaluate("el => el.outerHTML")
    path.write_text(html, encoding="utf-8")
    return str(path)


async def _document_list_snapshot(page: Page) -> str:
    parts = []
    try:
        parts.append(f"url={page.url}")
    except Exception:
        pass
    try:
        parts.append(f"table_count={await page.locator(DOC_TABLE).count()}")
    except Exception:
        pass
    try:
        parts.append(f"row_count={await page.locator(DOC_ROWS).count()}")
    except Exception:
        pass
    try:
        headers = await page.locator("#main-list-document th").all_inner_texts()
        cleaned = [re.sub(r"\s+", " ", text).strip() for text in headers if text.strip()]
        if cleaned:
            parts.append(f"headers={' | '.join(cleaned[:12])}")
    except Exception:
        pass
    try:
        screenshot_path = await _save_debug_screenshot(page, prefix="ecm_empty_docs")
        parts.append(f"debug_screenshot={screenshot_path}")
    except Exception:
        logger.debug("ECM empty document screenshot save failed", exc_info=True)
    return " | ".join(parts)


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

    # Step 1: 상암AX센터가 접혀 있을 수 있으므로 명시적으로 펼친다.
    root_index = _tree_root_index()
    ax_node = _visible_tree_link(tree, ECM_TREE_ROOT, index=root_index)
    try:
        await ax_node.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
        await ax_node.scroll_into_view_if_needed(timeout=3000)
        await _open_tree_node(page, ax_node)
    except Exception as exc:
        snapshot = await _tree_text_snapshot(tree)
        raise RuntimeError(
            f"ECM 트리에서 '{ECM_TREE_ROOT}' 폴더 #{root_index + 1}을 찾거나 펼치지 못했습니다. "
            f"visible={snapshot}"
        ) from exc

    # Step 2: 연도 시험서비스 폴더 클릭/펼침 (예: "2026년 시험서비스")
    year_folder = _visible_tree_link(tree, re.compile(f"{year}.*시험서비스"))
    try:
        await year_folder.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
        await _open_tree_node(page, year_folder)
        await _click_tree_link(page, year_folder, expected_text=f"{year}년 시험서비스")
        await _wait_splash_done(page)
    except Exception as exc:
        snapshot = await _tree_text_snapshot(tree)
        raise RuntimeError(f"ECM 트리에서 {year}년 시험서비스 폴더를 찾지 못했습니다. visible={snapshot}") from exc

    # Step 3: 01 GS인증시험(1등급) 폴더 클릭/펼침
    test_type_folder = _visible_tree_link(tree, ECM_TREE_TEST_TYPE)
    try:
        await test_type_folder.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
        await _open_tree_node(page, test_type_folder)
        await _click_tree_link(page, test_type_folder, expected_text=ECM_TREE_TEST_TYPE)
        await _wait_splash_done(page)
    except Exception as exc:
        snapshot = await _tree_text_snapshot(tree)
        raise RuntimeError(f"ECM 트리에서 '{ECM_TREE_TEST_TYPE}' 폴더를 찾지 못했습니다. visible={snapshot}") from exc

    # Step 4: 프로젝트번호를 포함하는 폴더 클릭
    project_folder = _visible_tree_link(tree, project_number)
    try:
        await project_folder.wait_for(state="visible", timeout=t["FOLDER_SEARCH"])
        await _click_tree_link(page, project_folder, expected_text=project_number)
        await _wait_splash_done(page)
        if not await _selected_tree_text_contains(tree, project_number):
            await _select_tree_node_by_text(page, project_number)
            await _wait_splash_done(page)
        await _verify_selected_project(tree, project_number)
    except Exception as exc:
        snapshot = await _tree_text_snapshot(tree)
        raise RuntimeError(f"ECM 트리에서 프로젝트 폴더를 찾지 못했습니다: {project_number}. visible={snapshot}") from exc


async def _open_tree_node(page: Page, node) -> None:
    await node.scroll_into_view_if_needed(timeout=3000)
    result = await node.evaluate(
        """
        (el) => {
          const root = document.querySelector('#edm-folder');
          const li = el.closest('li');
          if (!root || !li) {
            return { ok: false, reason: 'tree root or li not found' };
          }
          if ((li.className || '').includes('jstree-open')) {
            return { ok: true, method: 'already-open', id: li.id, className: li.className };
          }
          if (window.jQuery && window.jQuery.fn && window.jQuery.fn.jstree && li.id) {
            window.jQuery(root).jstree('open_node', li.id);
            return { ok: true, method: 'jstree-open-node', id: li.id, className: li.className };
          }
          const icon = li.querySelector(':scope > ins.jstree-icon');
          if (icon) {
            icon.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
            icon.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
            icon.click();
            return { ok: true, method: 'icon-click', id: li.id, className: li.className };
          }
          return { ok: false, reason: 'expand icon not found', id: li.id, className: li.className };
        }
        """
    )
    if not result or not result.get("ok"):
        raise RuntimeError(f"ECM 트리 노드 펼침 실패: {result}")
    logger.info("ECM tree node open requested: %s", result)
    await page.wait_for_timeout(1000)


async def _click_tree_link(page: Page, node, *, expected_text: str) -> None:
    await node.scroll_into_view_if_needed(timeout=3000)
    await node.click(timeout=3000, force=True)
    await page.wait_for_timeout(500)
    try:
        text = re.sub(r"\s+", " ", await node.inner_text()).strip()
    except Exception:
        text = ""
    logger.info("ECM tree node clicked: expected=%s actual=%s", expected_text, text)


async def _select_tree_node_by_text(page: Page, text: str) -> None:
    selected = await page.evaluate(
        """
        (text) => {
          const root = document.querySelector('#edm-folder');
          if (!root) {
            return { ok: false, reason: 'tree root not found' };
          }
          const links = Array.from(root.querySelectorAll('a'));
          const link = links.find((el) => (el.textContent || '').includes(text));
          if (!link) {
            return { ok: false, reason: 'node text not found', count: links.length };
          }
          link.scrollIntoView({ block: 'center', inline: 'nearest' });
          const li = link.closest('li');
          if (window.jQuery && window.jQuery.fn && window.jQuery.fn.jstree && li && li.id) {
            window.jQuery(root).jstree('deselect_all');
            window.jQuery(root).jstree('select_node', li.id);
            return { ok: true, method: 'jstree', text: link.textContent || '', id: li.id };
          }
          link.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
          link.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
          link.click();
          return { ok: true, method: 'dom-click', text: link.textContent || '', id: li ? li.id : '' };
        }
        """,
        text,
    )
    if not selected or not selected.get("ok"):
        raise RuntimeError(f"프로젝트 폴더 DOM 선택 실패: {selected}")
    logger.info("ECM tree node selected by text: %s", selected)


def _visible_tree_link(tree, text_or_pattern, *, index: int = 0):
    return tree.locator("a:visible").filter(has_text=text_or_pattern).nth(index)


async def _tree_text_snapshot(tree, *, limit: int = 40) -> str:
    try:
        texts = await tree.locator("a").all_inner_texts()
    except Exception:
        return "<tree text unavailable>"
    cleaned = [re.sub(r"\s+", " ", text).strip() for text in texts if text.strip()]
    if not cleaned:
        return "<empty>"
    return " | ".join(cleaned[:limit])


async def _verify_selected_project(tree, project_number: str) -> None:
    if await _selected_tree_text_contains(tree, project_number):
        return
    selected_text = await _selected_tree_text(tree)
    raise RuntimeError(f"프로젝트 폴더 선택 확인 실패: selected={selected_text or '<none>'}")


async def _selected_tree_text_contains(tree, text: str) -> bool:
    return text in await _selected_tree_text(tree)


async def _selected_tree_text(tree) -> str:
    try:
        selected = await tree.locator("a.jstree-clicked").all_inner_texts()
    except Exception:
        selected = []
    selected_text = " | ".join(re.sub(r"\s+", " ", text).strip() for text in selected if text.strip())
    return selected_text


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

    checkbox = page.locator(SELECT_ALL_CHECKBOX).first
    try:
        await checkbox.check(timeout=3000, force=True)
    except Exception:
        await checkbox.click(timeout=3000, force=True)
    try:
        if not await checkbox.is_checked():
            await checkbox.click(timeout=3000, force=True)
    except Exception:
        logger.debug("select-all checked state 확인 실패", exc_info=True)
    return count


async def click_download_menu(page: Page) -> None:
    """고급 메뉴 → 파일 다운로드 항목을 클릭한다."""
    t = _timeouts()

    btn = page.locator(ADVANCED_MENU_BTN)
    await btn.click(timeout=3000)

    menu = page.locator(CONTEXT_MENU)
    await menu.wait_for(state="visible", timeout=t["MENU_VISIBLE"])
    await _save_debug_screenshot(page, prefix="ecm_download_menu")
    await _save_debug_html(menu, prefix="ecm_download_menu")
    menu_items = await _visible_menu_items(menu)
    logger.info("ECM download menu items: %s", menu_items)

    item = page.locator(DOWNLOAD_MENU_ITEM).first
    if await item.count() > 0:
        await item.wait_for(state="visible", timeout=3000)
        await item.click(timeout=3000, force=True)
    else:
        text_item = menu.locator("li:visible").filter(has_text=re.compile("다운로드|저장")).first
        if await text_item.count() > 0:
            await text_item.click(timeout=3000, force=True)
        else:
            logger.warning("menuevent/text selector 실패, fallback selector 사용")
            fallback = page.locator(DOWNLOAD_MENU_FALLBACK)
            await fallback.click(timeout=3000, force=True)
    await page.wait_for_timeout(1000)
    await _save_debug_screenshot(page, prefix="ecm_after_download_click")


async def _visible_menu_items(menu) -> str:
    try:
        texts = await menu.locator("li:visible").all_inner_texts()
    except Exception:
        return "<menu text unavailable>"
    cleaned = [re.sub(r"\s+", " ", text).strip() for text in texts if text.strip()]
    return " | ".join(cleaned) if cleaned else "<empty>"


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
            snapshot = await _document_list_snapshot(page)
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
                error_message=f"{project_number} 프로젝트의 문서 목록이 비어 있습니다. {snapshot}",
            )

        await _save_debug_screenshot(page, prefix="ecm_docs_selected")
        await click_download_menu(page)
        return DownloadStepResult(success=True, doc_count=doc_count, page=page)

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
    if async_playwright is None:
        raise RuntimeError(
            "Playwright가 설치되지 않았습니다. live 다운로드 자동화는 "
            "requirements-automation.txt 설치 후 실행하세요."
        )
    pw = await async_playwright().start()
    try:
        launch_options = {
            "headless": headless,
            "args": _browser_args(),
        }
        channel = _browser_channel()
        if channel:
            launch_options["channel"] = channel
        browser = await pw.chromium.launch(**launch_options)
    except Exception:
        await pw.stop()
        raise
    _PLAYWRIGHT_BY_BROWSER_ID[id(browser)] = pw
    return browser


async def close_browser(browser: Browser) -> None:
    pw = _PLAYWRIGHT_BY_BROWSER_ID.pop(id(browser), None)
    try:
        await browser.close()
    except Exception:
        pass
    if pw is not None:
        try:
            await pw.stop()
        except Exception:
            pass
