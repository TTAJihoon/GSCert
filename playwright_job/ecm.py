import re
from typing import Dict, Pattern

from playwright.async_api import Page

from .common import (
    ECM_BASE_URL,
    TIMEOUTS,
    parse_cert_date,
    clipboard_set_text,
    wait_clipboard_nonempty,
)
from .selectors import (
    LEFT_PANEL_MENU,
    FOLDER_PANEL_ACTIVE,
    FOLDER_TREE,
    SPLASHSCREEN,
    CONTENT_TITLE_TEXT,
    DOC_TABLE,
    DOC_ROOT,
    DOC_CLICK_SPAN_IN_ROW,
    FILE_ROW,
    URL_COPY_BTN,
)


async def wait_loading_done(page: Page) -> None:
    # hidden은 "없음/숨김" 둘 다 통과 → 안전
    await page.locator(SPLASHSCREEN).wait_for(state="hidden", timeout=TIMEOUTS["SPLASH"])


async def goto_base(page: Page) -> Dict:
    resp = await page.goto(ECM_BASE_URL, timeout=TIMEOUTS["GOTO"], wait_until="domcontentloaded")
    if resp is None:
        raise RuntimeError("응답 없음")
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status}")
    await wait_loading_done(page)
    return {"status": resp.status}


async def wait_left_tree(page: Page) -> Dict:
    await page.locator(LEFT_PANEL_MENU).wait_for(state="visible", timeout=TIMEOUTS["LEFT_TREE"])
    await page.locator(FOLDER_PANEL_ACTIVE).wait_for(state="visible", timeout=TIMEOUTS["LEFT_TREE"])
    await page.locator(FOLDER_TREE).wait_for(state="visible", timeout=TIMEOUTS["LEFT_TREE"])
    return {}


async def _click_tree_text(page: Page, text: str) -> None:
    tree = page.locator(FOLDER_TREE)
    await tree.get_by_text(text).first.click(timeout=TIMEOUTS["TREE_CLICK"])
    await wait_loading_done(page)


async def click_year(page: Page, year: str) -> Dict:
    # "2025 시험서비스" 우선 → 실패 시 year만
    try:
        await _click_tree_text(page, f"{year} 시험서비스")
    except Exception:
        await _click_tree_text(page, year)
    return {}


async def click_committee(page: Page) -> Dict:
    await _click_tree_text(page, "GS인증심의위원회")
    return {}


async def click_date_folder(page: Page, cert_date_yyyymmdd: str) -> Dict:
    await _click_tree_text(page, cert_date_yyyymmdd)
    return {}


async def click_test_folder(page: Page, test_no: str) -> Dict:
    await _click_tree_text(page, test_no)
    # 타이틀에 test_no가 반영될 시간을 조금 줌(로딩 완료 후에도 DOM 반영 지연 케이스)
    await page.locator(CONTENT_TITLE_TEXT).wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
    return {}


async def click_document_in_list(page: Page, test_no_pat: Pattern) -> Dict:
    """
    ✅ 핵심 수정:
    - count()로 즉시 판정하면 로딩 지연에 취약 → 'visible 대기' 방식으로 변경
    - 문서명에 '자. ' 같은 접두가 붙어도 시험번호 포함이면 매칭
    - 우선순위: (1) '시험성적서' 포함 문서가 있으면 그걸 클릭
              (2) 없으면 시험번호 포함 문서를 클릭
    """
    await page.locator(DOC_TABLE).wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])

    spans = page.locator(f"{DOC_ROOT} {DOC_CLICK_SPAN_IN_ROW}")

    # 1) '시험성적서' 포함 문서가 먼저 뜨면 그걸 클릭
    score_span = spans.filter(has_text="시험성적서").first
    try:
        await score_span.wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
        await score_span.click(timeout=TIMEOUTS["DOC_CLICK"])
        await wait_loading_done(page)
        return {"picked": "시험성적서(문서)"}
    except Exception:
        pass

    # 2) 아니면 시험번호 포함 문서를 기다렸다가 클릭
    test_span = spans.filter(has_text=test_no_pat).first
    await test_span.wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
    await test_span.click(timeout=TIMEOUTS["DOC_CLICK"])
    await wait_loading_done(page)
    return {"picked": "시험번호(문서)"}


async def wait_file_list(page: Page) -> Dict:
    rows = page.locator(FILE_ROW)
    await rows.first.wait_for(state="visible", timeout=TIMEOUTS["FILE_LIST"])
    cnt = await rows.count()
    if cnt < 1:
        raise RuntimeError("파일 목록 0건")
    return {"file_count": cnt}


async def select_target_file_and_copy_url(page: Page, test_no_pat: Pattern) -> Dict:
    """
    ✅ 조건:
    1) 한 번 더 찾지 말고: '시험성적서' 포함 row 있으면 선택하고 진행
    2) 없으면: 시험번호 포함 row 선택하고 진행
    3) 같은 내용이 복사돼도 실패하지 않게: clipboard를 ""로 비우고 시작
    4) 복사된 텍스트에서 URL 파싱
    """
    rows = page.locator(FILE_ROW)

    # 1) 시험성적서 포함 row 우선
    target = rows.filter(has_text="시험성적서").first
    try:
        await target.wait_for(state="visible", timeout=TIMEOUTS["FILE_LIST"])
    except Exception:
        # 2) 없으면 시험번호 포함 row
        target = rows.filter(has_text=test_no_pat).first
        await target.wait_for(state="visible", timeout=TIMEOUTS["FILE_LIST"])

    # 체크박스 선택
    checkbox = target.locator('input[type="checkbox"]').first
    await checkbox.check(timeout=TIMEOUTS["DOC_CLICK"])

    # ✅ 같은 내용 복사여도 실패 방지: 미리 비움
    await clipboard_set_text("")

    btn = page.locator(URL_COPY_BTN).first
    await btn.wait_for(state="visible", timeout=TIMEOUTS["COPY_WAIT"])
    await btn.click(timeout=TIMEOUTS["DOC_CLICK"])

    pasted = await wait_clipboard_nonempty(timeout_ms=TIMEOUTS["COPY_WAIT"])
    if not pasted:
        raise RuntimeError("클립보드 변화 없음")

    # 여러 줄이면 첫 줄부터 URL 찾기
    m = re.search(r"(https?://\S+)", pasted)
    if not m:
        raise RuntimeError("URL 파싱 실패")

    return {"url": m.group(1)}


async def run_ecm_flow(page: Page, cert_date: str, test_no: str, test_no_pat: Pattern) -> Dict:
    """
    ecm.py 내부에서 전체 흐름을 한 번에 돌리고 싶을 때 사용(선택)
    tasks.py는 step 분리를 위해 보통 이걸 직접 안 씀.
    """
    year, yyyymmdd = parse_cert_date(cert_date)
    await goto_base(page)
    await wait_left_tree(page)
    await click_year(page, year)
    await click_committee(page)
    await click_date_folder(page, yyyymmdd)
    await click_test_folder(page, test_no)
    await click_document_in_list(page, test_no_pat)
    await wait_file_list(page)
    return await select_target_file_and_copy_url(page, test_no_pat)
