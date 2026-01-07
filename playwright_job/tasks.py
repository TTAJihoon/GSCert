import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Pattern

from playwright.async_api import Browser, Page, Locator, expect

# Windows clipboard
try:
    import win32clipboard
    import win32con
except ImportError:
    win32clipboard = None
    win32con = None

logger = logging.getLogger("playwright_job.task")

ECM_BASE_URL = "http://210.104.181.10"


# ----------------------------
# Config (확정/조정 가능한 값)
# ----------------------------
TO_GOTO_MS = 10_000
TO_TREE_MS = 8_000
TO_CLICK_MS = 5_000
TO_DOC_LIST_MS = 8_000
TO_FILE_LIST_MS = 8_000
TO_COPY_WAIT_MS = 5_000

# Step2 확정 (네 HTML 기준)
LEFT_ACTIVE_FOLDER_PANEL_SEL = (
    'div.edm-left-panel-menu-sub-item[submenu_type="Folder"].ui-accordion-content-active'
)
LEFT_TREE_ROOT_SEL = f"{LEFT_ACTIVE_FOLDER_PANEL_SEL} #edm-folder"

# 기존 코드에서 쓰던 selector들(일단 유지)
DOC_LIST_ITEM_SEL = 'span[events="document-list-viewDocument-click"]'
FILE_ROW_SEL = "tr.prop-view-file-list-item"
URL_COPY_BTN_SEL = "div#prop-view-document-btn-url-copy"


# ----------------------------
# Utilities
# ----------------------------
@dataclass
class StepError(RuntimeError):
    step_no: int
    step_msg: str
    debug: str = ""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _fmt_kv(**kwargs) -> str:
    parts = []
    for k, v in kwargs.items():
        if v is None:
            continue
        s = str(v)
        if len(s) > 120:
            s = s[:117] + "..."
        parts.append(f"{k}={s}")
    return " ".join(parts)


async def _run_step(step_no: int, msg: str, coro, **debug_kv):
    t0 = _now_ms()
    logger.info("S%d START | %s | %s", step_no, msg, _fmt_kv(**debug_kv))
    try:
        out = await coro
        dt = _now_ms() - t0
        logger.info("S%d OK | %s | %s | %dms", step_no, msg, _fmt_kv(**debug_kv), dt)
        return out
    except Exception as e:
        dt = _now_ms() - t0
        logger.error(
            "S%d FAIL(%s) | %s | %s | %dms",
            step_no, type(e).__name__, msg, _fmt_kv(**debug_kv), dt
        )
        raise StepError(step_no=step_no, step_msg=msg, debug=_fmt_kv(**debug_kv)) from e


def _get_date_parts(cert_date: str) -> tuple[str, str]:
    m = re.match(r'^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$', cert_date or '')
    if not m:
        raise ValueError(f"날짜 형식이 'yyyy.mm.dd' 또는 'yyyy-mm-dd'가 아닙니다: {cert_date}")
    y, mth, d = m.groups()
    return y, f"{y}{mth.zfill(2)}{d.zfill(2)}"


def _testno_pat(test_no: str) -> Pattern:
    safe_no = re.escape(test_no).replace(r'\-', "[-_]")
    return re.compile(safe_no, re.IGNORECASE)


def _get_clipboard_text_sync() -> str:
    if win32clipboard is None or win32con is None:
        raise RuntimeError("pywin32(win32clipboard, win32con)가 설치되어 있지 않습니다.")
    text = ""
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    return text or ""


async def _get_clipboard_text(retries: int = 5, delay_sec: float = 0.05) -> str:
    last_exc: Optional[Exception] = None
    for _ in range(retries):
        try:
            return await asyncio.to_thread(_get_clipboard_text_sync)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 읽기 실패: {last_exc}")


async def _wait_clipboard_change(before: str, timeout_ms: int, interval_ms: int = 100) -> str:
    elapsed = 0
    while elapsed < timeout_ms:
        cur = ""
        try:
            cur = await _get_clipboard_text()
        except Exception:
            cur = ""
        if cur and cur != before:
            return cur
        await asyncio.sleep(interval_ms / 1000.0)
        elapsed += interval_ms
    return ""


async def _pick_unique(locator: Locator, label: str) -> Locator:
    cnt = await locator.count()
    if cnt != 1:
        raise RuntimeError(f"{label} 후보가 1개가 아닙니다. count={cnt}")
    return locator.first


# ----------------------------
# Main task (Step1~Step10)
# ----------------------------
async def run_playwright_task_on_page(page: Page, cert_date: str, test_no: str) -> Dict[str, str]:
    year, date_key = _get_date_parts(cert_date)
    test_pat = _testno_pat(test_no)

    screenshot_path = None
    try:
        # Step 1: goto
        async def _s1():
            resp = await page.goto(ECM_BASE_URL, timeout=TO_GOTO_MS, wait_until="domcontentloaded")
            status = resp.status if resp else None
            url_after = page.url
            # 이동 성공 기준(초안): 예외 없이 goto 완료 + (status가 있으면 400 미만)
            if status is not None and status >= 400:
                raise RuntimeError(f"HTTP status >= 400: {status}")
            if not url_after.startswith(ECM_BASE_URL):
                # 리다이렉트가 있을 수 있어 “실패”로 할지 “경고”로 할지 정책 선택 가능.
                # 일단 실패로 둠.
                raise RuntimeError(f"Unexpected URL after goto: {url_after}")
            return {"status": status, "url": url_after}

        s1_out = await _run_step(
            1,
            "ECM 페이지 이동",
            _s1(),
            base_url=ECM_BASE_URL,
        )

        # Step 2: wait active folder tree panel
        async def _s2():
            panels = page.locator("div.edm-left-panel-menu-sub-item")
            active_folder = page.locator(LEFT_ACTIVE_FOLDER_PANEL_SEL)
            tree_root = page.locator(LEFT_TREE_ROOT_SEL)

            total_panels = await panels.count()
            active_cnt = await active_folder.count()

            # 핵심: "Folder 활성 패널" + "edm-folder"가 visible 되기까지 대기
            await active_folder.wait_for(state="visible", timeout=TO_TREE_MS)
            await tree_root.wait_for(state="visible", timeout=TO_TREE_MS)

            # 기다린 후 재확인(로그용)
            active_cnt2 = await active_folder.count()
            return {
                "total_panels": total_panels,
                "active_folder_cnt": active_cnt2,
            }

        s2_out = await _run_step(
            2,
            "좌측 트리(전사 폴더) 패널 로딩 대기",
            _s2(),
            selector=LEFT_ACTIVE_FOLDER_PANEL_SEL,
        )

        # Step 3: tree clicks (year -> GS인증심의위원회 -> date_key -> test_no)
        async def _s3():
            tree = page.locator(LEFT_TREE_ROOT_SEL)
            # get_by_text는 기본적으로 부분일치라 "2026"이 "2026 시험서비스"에 매칭 가능
            await tree.get_by_text(year).click(timeout=TO_CLICK_MS)
            await tree.get_by_text("GS인증심의위원회").click(timeout=TO_CLICK_MS)
            await tree.get_by_text(date_key).click(timeout=TO_CLICK_MS)
            await tree.get_by_text(test_no).click(timeout=TO_CLICK_MS)

        await _run_step(
            3,
            "좌측 트리 경로 클릭(연도→위원회→일자→시험번호)",
            _s3(),
            year=year,
            date_key=date_key,
            test_no=test_no,
        )

        # Step 4: wait doc list
        async def _s4():
            await page.wait_for_selector(DOC_LIST_ITEM_SEL, timeout=TO_DOC_LIST_MS)
            loc = page.locator(DOC_LIST_ITEM_SEL)
            return {"doc_items": await loc.count()}

        s4_out = await _run_step(
            4,
            "문서 목록 로딩 대기",
            _s4(),
            selector=DOC_LIST_ITEM_SEL,
        )

        # Step 5: pick and click target document (시험번호 포함 + 시험성적서 우선)
        async def _s5():
            doc_list = page.locator(DOC_LIST_ITEM_SEL)
            by_test = doc_list.filter(has_text=test_pat)
            cnt_by_test = await by_test.count()

            target = by_test.filter(has_text="시험성적서")
            cnt_target = await target.count()

            clicked_text = None

            if cnt_target == 1:
                await target.first.click(timeout=TO_CLICK_MS)
                clicked_text = (await target.first.inner_text()).strip()
                return {
                    "cnt_by_test": cnt_by_test,
                    "cnt_target": cnt_target,
                    "clicked": "시험성적서",
                    "clicked_text": clicked_text
                }

            fallback = by_test.filter(has_not_text="품질평가보고서")
            cnt_fb = await fallback.count()
            if cnt_fb == 1:
                await fallback.first.click(timeout=TO_CLICK_MS)
                clicked_text = (await fallback.first.inner_text()).strip()
                return {
                    "cnt_by_test": cnt_by_test,
                    "cnt_target": cnt_target,
                    "cnt_fallback": cnt_fb,
                    "clicked": "fallback",
                    "clicked_text": clicked_text
                }

            raise RuntimeError(
                f"대상 문서 확정 실패: by_test={cnt_by_test}, target(시험성적서)={cnt_target}, fallback={cnt_fb}"
            )

        s5_out = await _run_step(
            5,
            "문서 목록에서 대상 문서 선택/클릭",
            _s5(),
            test_no=test_no,
        )

        # Step 6: wait file list (파일 목록이 떴는데도 못 봤다고 판단 방지 → attached 기준으로)
        async def _s6():
            # 'visible' 말고 'attached'로 기다리면 display/가림 문제로 인한 오판이 줄어듦
            await page.wait_for_selector(FILE_ROW_SEL, timeout=TO_FILE_LIST_MS, state="attached")
            rows = page.locator(FILE_ROW_SEL)
            return {"rows_attached": await rows.count()}

        s6_out = await _run_step(
            6,
            "파일 목록 로딩 대기",
            _s6(),
            selector=FILE_ROW_SEL,
        )

        # Step 7: pick file row + checkbox check
        async def _s7():
            rows = page.locator(FILE_ROW_SEL)
            target_row = rows.filter(has_text=test_pat).filter(has_text="시험성적서")
            cnt = await target_row.count()
            if cnt != 1:
                raise RuntimeError(f"시험성적서 파일 행 확정 실패. count={cnt}")
            cb = target_row.first.locator('input[type="checkbox"]')
            await cb.check(timeout=TO_CLICK_MS)
            return {"target_rows": cnt}

        await _run_step(
            7,
            "시험성적서 파일 행 체크박스 선택",
            _s7(),
            row_selector=FILE_ROW_SEL,
        )

        # Step 8: click url copy
        async def _s8():
            btn = page.locator(URL_COPY_BTN_SEL)
            cnt = await btn.count()
            if cnt < 1:
                raise RuntimeError("URL 복사 버튼을 찾지 못했습니다.")
            await btn.first.click(timeout=TO_CLICK_MS)
            return {"btn_count": cnt}

        # 클릭 전 클립보드 저장(9에서 사용)
        if win32clipboard is None or win32con is None:
            raise RuntimeError("pywin32가 없어 OS 클립보드를 사용할 수 없습니다.")

        before_clip = await _get_clipboard_text()

        s8_out = await _run_step(
            8,
            "URL 복사 버튼 클릭",
            _s8(),
            selector=URL_COPY_BTN_SEL,
        )

        # Step 9: clipboard wait + parse URL
        async def _s9():
            pasted = await _wait_clipboard_change(before_clip, timeout_ms=TO_COPY_WAIT_MS)
            if not pasted:
                raise RuntimeError("클립보드 변화 없음(타임아웃 또는 빈값)")
            first_line = pasted.splitlines()[0]
            m = re.search(r"(https?://\S+)", first_line)
            if not m:
                raise RuntimeError("클립보드 첫 줄에서 URL 파싱 실패")
            return {"url": m.group(1), "clip_len": len(pasted)}

        s9_out = await _run_step(
            9,
            "클립보드에서 URL 추출",
            _s9(),
            timeout_ms=TO_COPY_WAIT_MS,
        )

        # Step 10: return
        async def _s10():
            return {"url": s9_out["url"]}

        out = await _run_step(
            10,
            "결과 반환",
            _s10(),
            url=s9_out["url"],
        )
        return out

    except Exception as e:
        # 최상위 실패 처리: 스크린샷 + 한 줄 요약
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"playwright_error_{ts}.png"
        try:
            await page.screenshot(path=screenshot_path)
        except Exception:
            screenshot_path = None

        if isinstance(e, StepError):
            logger.error(
                "ECM 작업 실패 | step=%s msg=%s debug=%s screenshot=%s",
                e.step_no, e.step_msg, e.debug, screenshot_path
            )
        else:
            logger.error(
                "ECM 작업 실패 | step=? msg=%s screenshot=%s",
                str(e), screenshot_path
            )
        raise


async def run_playwright_task(browser: Browser, cert_date: str, test_no: str) -> Dict[str, str]:
    context = await browser.new_context()
    page = await context.new_page()
    try:
        return await run_playwright_task_on_page(page, cert_date, test_no)
    finally:
        try:
            await context.close()
        except Exception:
            pass
