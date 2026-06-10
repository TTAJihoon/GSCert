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
    FILE_SAVE_BTN,
    URL_COPY_BTN,
)


TREE_LINK = 'a[menuname="edm-folder-context-tree"]'
COMMITTEE_ROOT_PATTERN = re.compile(r"^\s*00\s+\d{4}년\s+GS인증심의위원회\s*$")
COMMITTEE_ROUND_PATTERN = re.compile(r"^\s*\d{2}.*품질인증심의위원회")
REPORT_DOCUMENT_NAME = "시험성적서"


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


async def _click_tree_anchor(page: Page, anchor) -> None:
    await anchor.scroll_into_view_if_needed(timeout=TIMEOUTS["TREE_CLICK"])
    await anchor.click(timeout=TIMEOUTS["TREE_CLICK"], force=True)
    await wait_loading_done(page)


async def _open_tree_anchor(page: Page, anchor) -> None:
    result = await anchor.evaluate(
        """
        (el) => {
          const root = document.querySelector('#edm-folder');
          const li = el.closest('li');
          if (!root || !li) return { ok: false, reason: 'missing tree root or li' };
          if ((li.className || '').includes('jstree-open')) {
            return { ok: true, method: 'already-open' };
          }
          if (window.jQuery && window.jQuery.fn && window.jQuery.fn.jstree && li.id) {
            window.jQuery(root).jstree('open_node', li.id);
            return { ok: true, method: 'jstree-open-node' };
          }
          const icon = li.querySelector(':scope > ins.jstree-icon');
          if (!icon) return { ok: false, reason: 'missing expand icon' };
          icon.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
          icon.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
          icon.click();
          return { ok: true, method: 'icon-click' };
        }
        """
    )
    if not result or not result.get("ok"):
        raise RuntimeError(f"ECM tree open failed: {result}")
    await page.wait_for_timeout(800)


async def _direct_child_folders(anchor) -> list[dict]:
    return await anchor.evaluate(
        """
        (el) => {
          const li = el.closest('li');
          if (!li) return [];
          return Array.from(li.querySelectorAll(':scope > ul > li > a')).map((a, index) => ({
            index,
            name: a.getAttribute('name') || (a.textContent || '').trim(),
            text: (a.textContent || '').trim(),
            oid: a.getAttribute('oid') || '',
          }));
        }
        """
    )


async def _click_tree_child_by_oid(page: Page, oid: str) -> None:
    tree = page.locator(FOLDER_TREE)
    anchor = tree.locator(f'a[oid="{oid}"]').first
    await anchor.wait_for(state="visible", timeout=TIMEOUTS["TREE_CLICK"])
    await _click_tree_anchor(page, anchor)


def committee_target_child_folders(folder_names: list[str]) -> list[str]:
    cleaned = [str(name or "").strip() for name in folder_names if str(name or "").strip()]
    if len(cleaned) <= 2:
        return []
    return cleaned[1:-1]


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


async def click_committee_review_root(page: Page, year: str):
    tree = page.locator(FOLDER_TREE)
    root = tree.locator(TREE_LINK).filter(has_text=COMMITTEE_ROOT_PATTERN).first
    try:
        await root.wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
    except Exception:
        root = tree.locator(TREE_LINK).filter(has_text=f"00 {year}년 GS인증심의위원회").first
        await root.wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
    await _open_tree_anchor(page, root)
    await _click_tree_anchor(page, root)
    return root


async def list_committee_round_folders(page: Page, committee_root) -> list[dict]:
    await _open_tree_anchor(page, committee_root)
    folders = await _direct_child_folders(committee_root)
    return [
        folder
        for folder in folders
        if COMMITTEE_ROUND_PATTERN.search(folder.get("name", "") or folder.get("text", ""))
    ]


async def list_committee_target_folders(page: Page, round_folder: dict) -> list[dict]:
    oid = round_folder.get("oid")
    if not oid:
        raise RuntimeError(f"round folder oid missing: {round_folder}")
    await _click_tree_child_by_oid(page, oid)
    round_anchor = page.locator(FOLDER_TREE).locator(f'a[oid="{oid}"]').first
    await _open_tree_anchor(page, round_anchor)
    child_folders = await _direct_child_folders(round_anchor)
    target_names = set(committee_target_child_folders([item["name"] for item in child_folders]))
    return [item for item in child_folders if item["name"] in target_names]


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


async def click_report_document_in_list(page: Page, folder_name: str) -> Dict:
    await page.locator(DOC_TABLE).wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])

    spans = page.locator(f"{DOC_ROOT} {DOC_CLICK_SPAN_IN_ROW}")
    report_span = spans.filter(has_text=REPORT_DOCUMENT_NAME).first
    try:
        await report_span.wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
        await report_span.click(timeout=TIMEOUTS["DOC_CLICK"])
        await wait_loading_done(page)
        return {"picked": REPORT_DOCUMENT_NAME}
    except Exception:
        pass

    fallback_span = spans.filter(has_text=folder_name).first
    await fallback_span.wait_for(state="visible", timeout=TIMEOUTS["DOC_LIST"])
    await fallback_span.click(timeout=TIMEOUTS["DOC_CLICK"])
    await wait_loading_done(page)
    return {"picked": folder_name}


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


async def click_first_file_save_button(page: Page) -> Dict:
    rows = page.locator(FILE_ROW)
    await rows.first.wait_for(state="visible", timeout=TIMEOUTS["FILE_LIST"])
    save_btn = rows.first.locator(FILE_SAVE_BTN).first
    await save_btn.wait_for(state="visible", timeout=TIMEOUTS["FILE_LIST"])
    await save_btn.click(timeout=TIMEOUTS["DOC_CLICK"], force=True)
    return {"save_clicked": True}


async def run_committee_report_download_flow(page: Page, cert_date: str, after_save_click=None) -> Dict:
    if after_save_click is None:
        raise RuntimeError("after_save_click callback is required to handle the Windows folder popup")

    year, _ = parse_cert_date(cert_date)
    await goto_base(page)
    await wait_left_tree(page)
    await click_year(page, year)
    committee_root = await click_committee_review_root(page, year)

    downloaded = []
    skipped = []
    for round_folder in await list_committee_round_folders(page, committee_root):
        targets = await list_committee_target_folders(page, round_folder)
        for target in targets:
            folder_name = target["name"]
            try:
                await _click_tree_child_by_oid(page, target["oid"])
                picked = await click_report_document_in_list(page, folder_name)
                await wait_file_list(page)
                await click_first_file_save_button(page)
                await after_save_click({
                    "round": round_folder.get("name", ""),
                    "folder": folder_name,
                    "picked": picked.get("picked", ""),
                })
                downloaded.append({
                    "round": round_folder.get("name", ""),
                    "folder": folder_name,
                    "picked": picked.get("picked", ""),
                })
            except Exception as exc:
                skipped.append({
                    "round": round_folder.get("name", ""),
                    "folder": folder_name,
                    "error": str(exc),
                })

    return {"download_requested": len(downloaded), "downloaded": downloaded, "skipped": skipped}


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
