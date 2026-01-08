# myproject/playwright_job/ecm.py
from __future__ import annotations

from typing import Dict, Pattern

from playwright.async_api import Page

from .common import TIMEOUTS, StepError, screenshot_name, log_fail, parse_cert_date, compile_testno_pat
from .selectors import (
    LEFT_PANEL_MENU,
    FOLDER_PANEL_ACTIVE,
    FOLDER_TREE,
    DOC_TABLE,
    DOC_ROW_ALL,
    DOC_CLICK_SPAN_IN_ROW,
    FILE_ROW,
    URL_COPY_BTN,
)
from .clipboard import make_sentinel, set_clipboard_text, wait_clipboard_not_equal
from .parsers import pick_best_file_url
from .common import ECM_BASE_URL


# -------------------------
# internal runner
# -------------------------

async def _run_step(page: Page, step_no: int, error_kind: str, request_ip: str, coro):
    """
    step 실패 시:
      - 스크린샷 저장
      - log_fail(시간|IP|S#|오류종류|스크린샷) 1줄
      - StepError로 변환 (traceback 로그는 consumers/worker에서 안 찍음)
    """
    try:
        return await coro
    except StepError:
        raise
    except Exception:
        shot = screenshot_name()
        try:
            await page.screenshot(path=shot)
        except Exception:
            shot = f"{shot}(FAILED)"
        log_fail(request_ip, step_no, error_kind, shot)
        raise StepError(step_no=step_no, error_kind=error_kind, screenshot=shot, request_ip=request_ip)


# -------------------------
# helpers
# -------------------------

async def click_tree_by_text(page: Page, text: str, timeout_ms: int) -> None:
    tree = page.locator(FOLDER_TREE)
    loc = tree.get_by_text(text, exact=False).first
    await loc.wait_for(state="visible", timeout=timeout_ms)
    await loc.click(timeout=timeout_ms)


# -------------------------
# steps
# -------------------------

async def s1_goto(page: Page) -> Dict:
    resp = await page.goto(ECM_BASE_URL, timeout=TIMEOUTS.GOTO, wait_until="domcontentloaded")
    if resp is None:
        raise RuntimeError("페이지 이동 응답 없음")
    if resp.status >= 400:
        raise RuntimeError(f"페이지 이동 실패(HTTP {resp.status})")
    return {"http_status": resp.status}


async def s2_wait_left_tree(page: Page) -> Dict:
    await page.locator(LEFT_PANEL_MENU).wait_for(state="visible", timeout=TIMEOUTS.LEFT_TREE)
    await page.locator(FOLDER_PANEL_ACTIVE).wait_for(state="visible", timeout=TIMEOUTS.LEFT_TREE)
    await page.locator(FOLDER_TREE).wait_for(state="visible", timeout=TIMEOUTS.LEFT_TREE)
    return {}


async def s3_click_year(page: Page, year: str) -> Dict:
    # 임의 폴백 없이 "YYYY 시험서비스"만 클릭
    await click_tree_by_text(page, f"{year} 시험서비스", timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s4_click_committee(page: Page) -> Dict:
    await click_tree_by_text(page, "GS인증심의위원회", timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s5_click_date(page: Page, yyyymmdd: str) -> Dict:
    await click_tree_by_text(page, yyyymmdd, timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s6_click_test_folder(page: Page, test_no: str) -> Dict:
    await click_tree_by_text(page, test_no, timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s7_click_document(page: Page, test_no_pat: Pattern[str]) -> Dict:
    """
    문서 목록에서:
      1) '시험성적서' 포함 row가 있으면 그 row 클릭
      2) 없으면 시험번호 포함 row 클릭
    """
    await page.locator(DOC_TABLE).wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)

    rows = page.locator(DOC_ROW_ALL)
    await rows.first.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)

    # 1) 시험성적서 포함 row
    score_rows = rows.filter(has_text="시험성적서")
    if await score_rows.count() > 0:
        row = score_rows.first
        span = row.locator(DOC_CLICK_SPAN_IN_ROW).first
        await span.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)
        await span.scroll_into_view_if_needed()
        await span.click(timeout=TIMEOUTS.DOC_CLICK)
        return {"picked": "시험성적서"}

    # 2) 시험번호 포함 row
    test_rows = rows.filter(has_text=test_no_pat)
    if await test_rows.count() > 0:
        row = test_rows.first
        span = row.locator(DOC_CLICK_SPAN_IN_ROW).first
        await span.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)
        await span.scroll_into_view_if_needed()
        await span.click(timeout=TIMEOUTS.DOC_CLICK)
        return {"picked": "시험번호"}

    raise RuntimeError("문서 목록에서 대상 row를 찾지 못했습니다(시험성적서/시험번호 모두 없음)")


async def s8_wait_file_list(page: Page) -> Dict:
    rows = page.locator(FILE_ROW)
    await rows.first.wait_for(state="visible", timeout=TIMEOUTS.FILE_LIST)
    cnt = await rows.count()
    if cnt < 1:
        raise RuntimeError("파일 목록 0건")
    return {"file_count": cnt}


async def s9_copy_file_url(page: Page, test_no_pat: Pattern[str]) -> Dict:
    """
    파일 목록에서:
      1) '시험성적서' 포함 row가 있으면 그 row 기준으로 URL 복사
      2) 없으면 시험번호 포함 row 기준으로 URL 복사
    그리고 클립보드에서 파일 URL만 엄격 파싱(임의 폴백 없음).
    - 같은 내용 복사여도 실패하지 않도록 sentinel 사용
    """
    rows = page.locator(FILE_ROW)

    # 1) 시험성적서 row 우선
    target = rows.filter(has_text="시험성적서")
    if await target.count() > 0:
        row = target.first
        picked = "시험성적서"
    else:
        # 2) 없으면 시험번호 포함
        target2 = rows.filter(has_text=test_no_pat)
        if await target2.count() == 0:
            raise RuntimeError("URL 복사 대상 파일 row를 찾지 못했습니다(시험성적서/시험번호 모두 없음)")
        row = target2.first
        picked = "시험번호"

    # ✅ 선택 상태 보장: row를 한번 클릭해서 포커스/선택 상태 만들기
    await row.click(timeout=TIMEOUTS.COPY_URL)

    # 체크박스가 있으면 체크(없으면 패스)
    cb = row.locator('input[type="checkbox"]')
    if await cb.count() > 0:
        await cb.first.check(timeout=TIMEOUTS.COPY_URL)

    # sentinel 방식(같은 내용 복사여도 실패 X)
    sentinel = make_sentinel()
    await set_clipboard_text(sentinel)

    btn = page.locator(URL_COPY_BTN).first
    await btn.wait_for(state="visible", timeout=TIMEOUTS.COPY_URL)
    await btn.click(timeout=TIMEOUTS.COPY_URL)

    pasted = await wait_clipboard_not_equal(sentinel, timeout_ms=TIMEOUTS.COPY_URL)
    if not pasted:
        raise RuntimeError("URL 복사 후 클립보드 갱신을 확인하지 못했습니다")

    file_url = pick_best_file_url(pasted)
    if not file_url:
        raise RuntimeError("클립보드에서 파일 URL 파싱 실패(시험s: 시험성적서 줄/확장자 줄 없음)")

    return {"picked": picked, "file_url": file_url}


# -------------------------
# main entry
# -------------------------

async def run_ecm_flow(page: Page, cert_date: str, test_no: str, request_ip: str = "-") -> Dict[str, str]:
    """
    성공 시: {"file_url": "..."} 반환
    실패 시: StepError raise (step/screenshot 포함)
    """
    year, yyyymmdd = parse_cert_date(cert_date)
    test_no_pat = compile_testno_pat(test_no)

    await _run_step(page, 1, "페이지 이동 실패", request_ip, s1_goto(page))
    await _run_step(page, 2, "좌측 트리 로딩 실패", request_ip, s2_wait_left_tree(page))

    await _run_step(page, 3, "연도 폴더 클릭 실패", request_ip, s3_click_year(page, year))
    await _run_step(page, 4, "위원회 폴더 클릭 실패", request_ip, s4_click_committee(page))
    await _run_step(page, 5, "인증일자 폴더 클릭 실패", request_ip, s5_click_date(page, yyyymmdd))
    await _run_step(page, 6, "시험번호 폴더 클릭 실패", request_ip, s6_click_test_folder(page, test_no))

    await _run_step(page, 7, "문서 목록에서 대상 문서 클릭 실패", request_ip, s7_click_document(page, test_no_pat))
    await _run_step(page, 8, "파일 목록 로딩 실패", request_ip, s8_wait_file_list(page))

    out = await _run_step(page, 9, "URL 복사 실패", request_ip, s9_copy_file_url(page, test_no_pat))
    return {"file_url": out["file_url"]}
