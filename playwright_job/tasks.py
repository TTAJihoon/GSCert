import re
from playwright.async_api import Browser, Page, expect

def _get_date_parts(cert_date: str) -> tuple[str, str]:
    """ 'yyyy.mm.dd' 형식의 날짜를 'yyyy', 'yyyymmdd'로 분리 """
    parts = cert_date.split('.')
    if len(parts) != 3:
        raise ValueError("날짜 형식이 'yyyy.mm.dd'가 아닙니다.")
    year, month, day = parts
    return year, f"{year}{month}{day}"

def _testno_pat(test_no: str) -> re.Pattern:
    """ 시험번호의 구분자(하이픈/언더스코어)를 동일하게 취급하는 정규식 생성 """
    safe_no = re.escape(test_no).replace(r"\\-", r"[-_]")
    return re.compile(safe_no, re.IGNORECASE)

async def _prime_copy_sniffer(page: Page):
    """ 클립보드 복사 이벤트를 가로채는 JS 코드 주입 """
    inject_js = r"""
    (() => {
        if (window.__copy_sniffer_installed) return;
        window.__copy_sniffer_installed = true;
        window.__last_copied = '';
        const _origWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
        navigator.clipboard.writeText = async (t) => {
            window.__last_copied = t;
            return _origWrite(t);
        };
    })();
    """
    await page.add_init_script(inject_js)
    await page.evaluate(inject_js)

async def _get_sniffed_text(page: Page) -> str:
    """ 주입된 스니퍼를 통해 복사된 텍스트를 가져옴 """
    return await page.evaluate("() => window.__last_copied || ''")

# --- Main Task Function ---

async def run_playwright_task(browser: Browser, cert_date: str, test_no: str) -> dict:
    # 1. 입력값 처리
    year, date_str = _get_date_parts(cert_date)

    # 2. 새롭고 깨끗한 '브라우저 컨텍스트' 생성
    context = await browser.new_context()
    page = await context.new_page()

    try:
        # 3. 왼쪽 트리 메뉴 탐색
        tree_selector = "div.edm-left-panel-menu-sub-item"
        await page.locator(tree_selector).get_by_text(year).click()
        await page.locator(tree_selector).get_by_text("GS인증심의위원회").click()
        await page.locator(tree_selector).get_by_text(date_str).click()
        await page.locator(tree_selector).get_by_text(test_no).click()
        
        # 4. 문서 목록에서 대상 클릭
        doc_list_selector = 'span[event="document-list-viewDocument-click"]'
        doc_list = page.locator(doc_list_selector)
        
        target_doc = doc_list.filter(has_text="시험성적서").first
        if await target_doc.count() == 0:
            target_doc = doc_list.filter(has_text=_testno_pat(test_no)).first
        
        await target_doc.click()

        # 5. 파일 목록에서 체크박스 선택
        file_list_selector = 'span[events="document-fileOpen-click"]'
        file_span = page.locator(file_list_selector).filter(has_text="시험성적서").first
        
        # span -> 부모 tr -> 그 안의 checkbox 찾기
        parent_tr = file_span.locator('xpath=./ancestor::tr')
        checkbox = parent_tr.locator('input[type="checkbox"]')
        await checkbox.check()

        # 6. 클립보드 복사 및 내용 읽기
        await _prime_copy_sniffer(page)
        await page.locator('div#prop-view-document-btn-url-copy').click()
        
        # 복사가 JS에 의해 처리될 시간을 잠시 기다림
        await page.wait_for_timeout(1000)
        copied_text = await _get_sniffed_text(page)

        if not copied_text:
            raise RuntimeError("클립보드에서 텍스트를 가져오지 못했습니다.")

        # 7. 최종 URL 추출 및 반환
        first_line = copied_text.splitlines()[0]
        match = re.search(r'https?://\S+', first_line)
        if not match:
            raise ValueError("복사된 텍스트의 첫 줄에서 URL을 찾을 수 없습니다.")

        return {'url': match.group(0)}

    finally:
        # 8. 작업 완료 후 컨텍스트를 닫아 모든 흔적(쿠키, 세션 등)을 제거
        await context.close()
