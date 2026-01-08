# ECM Playwright 자동화 로직(트리 이동 → 문서 클릭 → 파일목록 → URL 복사)

from __future__ import annotations

import re
from typing import Dict, Pattern

from playwright.async_api import Page

from .common import ECM_BASE_URL, TIMEOUTS
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


# -------------------------
# helpers
# -------------------------

def parse_cert_date(cert_date: str) -> tuple[str, str]:
    """
    'yyyy.mm.dd' 또는 'yyyy-mm-dd' -> ('yyyy', 'yyyymmdd')
    """
    m = re.match(r"^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$", cert_date or "")
    if not m:
        raise ValueError(f"날짜 형식 오류: {cert_date}")
    y, mo, d = m.groups()
    return y, f"{y}{mo.zfill(2)}{d.zfill(2)}"


def compile_testno_pat(test_no: str) -> Pattern[str]:
    # 시험번호 매칭(대소문자 무시). 하이픈/언더스코어 혼용은 여기선 강제하지 않음(임의 폴백 방지).
    return re.compile(re.escape(test_no), re.IGNORECASE)


async def click_tree_by_text(page: Page, text: str, timeout_ms: int) -> None:
    """
    좌측 트리(#edm-folder) 영역에서 'text'가 포함된 노드를 클릭.
    (트리 외 영역 오탐 방지)
    """
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
    # 좌측 메뉴/트리 표시 확인
    await page.locator(LEFT_PANEL_MENU).wait_for(state="visible", timeout=TIMEOUTS.LEFT_TREE)
    await page.locator(FOLDER_PANEL_ACTIVE).wait_for(state="visible", timeout=TIMEOUTS.LEFT_TREE)
    await page.locator(FOLDER_TREE).wait_for(state="visible", timeout=TIMEOUTS.LEFT_TREE)
    return {}


async def s3_click_year(page: Page, year: str) -> Dict:
    # 임의 폴백 없이: "YYYY 시험서비스" 노드 클릭만 수행
    await click_tree_by_text(page, f"{year} 시험서비스", timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s4_click_committee(page: Page) -> Dict:
    # "GS인증심의위원회" 포함 노드 클릭
    await click_tree_by_text(page, "GS인증심의위원회", timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s5_click_date(page: Page, yyyymmdd: str) -> Dict:
    # 인증일자(yyyymmdd)가 포함된 노드 클릭
    await click_tree_by_text(page, yyyymmdd, timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s6_click_test_folder(page: Page, test_no: str) -> Dict:
    # "가. GS-A-25-0173" 같은 텍스트에서 시험번호 포함으로 클릭
    await click_tree_by_text(page, test_no, timeout_ms=TIMEOUTS.CLICK_TREE)
    return {}


async def s7_click_document(page: Page, test_no_pat: Pattern[str]) -> Dict:
    """
    문서 목록에서:
    1) '시험성적서' 포함 row 우선 클릭
    2) 없으면 '시험번호 포함' row 클릭
    """
    await page.locator(DOC_TABLE).wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)

    rows = page.locator(DOC_ROW_ALL)

    # 1) 시험성적서 우선
    score_rows = rows.filter(has_text="시험성적서")
    if await score_rows.count() > 0:
        row = score_rows.first
        await row.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)
        span = row.locator(DOC_CLICK_SPAN_IN_ROW).first
        await span.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)
        await span.click(timeout=TIMEOUTS.DOC_CLICK)
        return {"picked": "시험성적서"}

    # 2) 없으면 시험번호 포함
    test_rows = rows.filter(has_text=test_no_pat)
    if await test_rows.count() > 0:
        row = test_rows.first
        await row.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)
        span = row.locator(DOC_CLICK_SPAN_IN_ROW).first
        await span.wait_for(state="visible", timeout=TIMEOUTS.DOC_CLICK)
        await span.click(timeout=TIMEOUTS.DOC_CLICK)
        return {"picked": "시험번호"}

    raise RuntimeError("문서 목록에서 대상 row를 찾지 못했습니다(시험성적서/시험번호 모두 없음)")


async def s8_wait_file_list(page: Page) -> Dict:
    """
    파일 목록은 0개일 수도 있지만,
    '일치하는 문서가 존재하고 클릭이 성공했다면' 최소 1개 이상 떠야 한다는 합의 반영.
    """
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
    그리고 클립보드 텍스트에서 '파일 URL'을 우선순위 파싱하여 반환.
    - 같은 내용 복사여도 실패하지 않도록 sentinel 방식 사용
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

    # 체크박스가 있으면 체크 (없으면 패스)
    cb = row.locator('input[type="checkbox"]')
    if await cb.count() > 0:
        await cb.first.check(timeout=TIMEOUTS.COPY_URL)

    # sentinel 방식: "복사 내용이 이전과 동일"해도 실패하지 않게 함
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
        raise RuntimeError("클립보드에서 파일 URL 파싱 실패")

    return {"picked": picked, "file_url": file_url, "clipboard": pasted}


# -------------------------
# main entry
# -------------------------

async def run_ecm_flow(page: Page, cert_date: str, test_no: str) -> Dict[str, str]:
    """
    ECM 자동화 전체 실행.
    성공 시: {"file_url": "..."} 반환
    실패 시: 예외를 그대로 raise (tasks.py 쪽에서 StepError/로그/스크린샷 정책 처리)
    """
    year, yyyymmdd = parse_cert_date(cert_date)
    test_no_pat = compile_testno_pat(test_no)

    await s1_goto(page)
    await s2_wait_left_tree(page)

    await s3_click_year(page, year)
    await s4_click_committee(page)
    await s5_click_date(page, yyyymmdd)
    await s6_click_test_folder(page, test_no)

    await s7_click_document(page, test_no_pat)
    await s8_wait_file_list(page)
    out = await s9_copy_file_url(page, test_no_pat)

    return {"file_url": out["file_url"]}
