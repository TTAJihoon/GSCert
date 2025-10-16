import asyncio
import re
from re import Pattern
from playwright.async_api import Browser, Page, Locator, expect

def _get_date_parts(cert_date: str) -> tuple[str, str]:
    """ 'yyyy.mm.dd' 형식의 날짜를 'yyyy', 'yyyymmdd'로 분리 """
    try:
        parts = cert_date.split('.')
        if len(parts) != 3: raise ValueError
        year, month, day = parts
        return year, f"{year}{month.zfill(2)}{day.zfill(2)}"
    except Exception:
        raise ValueError(f"날짜 형식이 'yyyy.mm.dd'가 아닙니다. 입력값: {cert_date}")

def _testno_pat(test_no: str) -> Pattern:
    """ 시험번호의 구분자(하이픈/언더스코어)를 동일하게 취급하는 정규식 생성 """
    # 정규식 특수 문자를 이스케이프 처리하고, 하이픈(-)만 정규식 패턴 [-] 또는 [_]로 변경
    safe_no = re.escape(test_no).replace(r'\-', "[-_]")
    return re.compile(safe_no, re.IGNORECASE)

async def _prime_copy_sniffer(page: Page):
    """
    클립보드 복사 파이프라인을 페이지 내부에서 안전하게 가로챈다.
    - navigator.clipboard.writeText
    - document 'copy' 캡처 이벤트
    - document.execCommand('copy') 래핑
    """
    inject_js = r"""
    (() => {
        if (window.__copy_sniffer_installed) return;
        window.__copy_sniffer_installed = true;
        window.__last_copied = '';
        window.__copy_seq = 0;  // 변화 감지용 시퀀스

        // 1) writeText 오버라이드
        if (navigator.clipboard && navigator.clipboard.writeText) {
            const _origWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
            navigator.clipboard.writeText = async (t) => {
                try { window.__last_copied = String(t || ''); window.__copy_seq++; } catch(e) {}
                return _origWrite(t);
            };
        }

        // 2) 'copy' 캡처 단계 이벤트 (execCommand/clipboardData 경로)
        document.addEventListener('copy', (e) => {
            try {
                let txt = '';
                if (e && e.clipboardData) {
                    txt = e.clipboardData.getData('text/plain') || '';
                }
                if (!txt && window.getSelection) {
                    txt = String(window.getSelection() || '');
                }
                if (txt) { window.__last_copied = String(txt); window.__copy_seq++; }
            } catch (err) {}
        }, true);

        // 3) execCommand('copy') 래핑 (구형 대비)
        const _origExec = document.execCommand ? document.execCommand.bind(document) : null;
        if (_origExec) {
            document.execCommand = function(command, ui, value) {
                try {
                    if ((command || '').toLowerCase() === 'copy') {
                        // selection 기반 복사 추정
                        const txt = String(window.getSelection ? (window.getSelection() || '') : '');
                        if (txt) { window.__last_copied = txt; window.__copy_seq++; }
                    }
                } catch (err) {}
                return _origExec(command, ui, value);
            };
        }
    })();
    """
    await page.add_init_script(inject_js)
    await page.evaluate(inject_js)

async def _get_sniffed_text(page: Page, last_seq_before: int, timeout_ms: int = 5000) -> str:
    """
    __copy_seq가 증가(새 복사 발생)할 때까지 짧게 폴링.
    발생하면 __last_copied 반환.
    """
    import math
    deadline = timeout_ms
    interval = 100
    tried = 0
    while tried * interval < deadline:
        seq, txt = await page.evaluate("""() => [window.__copy_seq|0, String(window.__last_copied||'')]""")
        if seq > last_seq_before and txt:
            return txt
        await page.wait_for_timeout(interval)
        tried += 1
    return ""


# --- Main Task Function (메인 작업 함수) ---
async def run_playwright_task(browser: Browser, cert_date: str, test_no: str) -> dict:
    """
    전달받은 브라우저 인스턴스를 사용하여 ECM 접속부터 URL 추출까지의 모든 작업을 수행합니다.
    """
    # 1. 입력값 처리
    year, date_str = _get_date_parts(cert_date)
    test_no_pattern = _testno_pat(test_no)

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

        # 4. 문서 목록에서 대상 클릭 (우선순위 적용)
        doc_list_selector = 'span[event="document-list-viewDocument-click"]'
        doc_list = page.locator(doc_list_selector)
        
        # 1순위: 시험번호와 '시험성적서'를 모두 포함하는 가장 정확한 대상
        target_doc = doc_list.filter(has_text=test_no_pattern).filter(has_text="시험성적서")
        
        clicked = False
        if await target_doc.count() == 1:
            await target_doc.click()
            clicked = True
        
        # 2순위: 1순위가 없으면, '품질평가보고서'를 제외한 대표 폴더/문서
        if not clicked:
            fallback_doc = doc_list.filter(has_text=test_no_pattern).filter(has_not_text="품질평가보고서")
            if await fallback_doc.count() == 1:
                await fallback_doc.click()
                clicked = True

        if not clicked:
            raise RuntimeError(f"문서 목록에서 '{test_no}'에 해당하는 정확한 대상을 찾지 못했습니다.")

        # 5. 파일 목록에서 체크박스 선택
        table_rows = page.locator("tr.prop-view-file-list-item")
        target_row = table_rows.filter(has_text=test_no_pattern).filter(has_text="시험성적서")
        
        await expect(target_row).to_have_count(1, timeout=10000) # 10초 내 정확히 1개 행이 되는지 확인
        checkbox = target_row.locator('input[type="checkbox"]')
        await checkbox.check()

        # 6. 클립보드 복사 및 내용 읽기 (안정한 방식)
        await _prime_copy_sniffer(page)
        # 복사 이전의 시퀀스 값을 읽어둔다
        last_seq_before = await page.evaluate("() => window.__copy_seq|0")

        await page.locator('div#prop-view-document-btn-url-copy').click()

        # 복사가 실제 발생할 때까지 최대 5초 대기(100ms 폴링)
        copied_text = await _get_sniffed_text(page, last_seq_before, timeout_ms=5000)
        if not copied_text:
            raise RuntimeError("복사 이벤트를 확인하지 못했습니다. (타임아웃)")

        # 7. 최종 URL 추출 및 반환
        first_line = copied_text.splitlines()[0]
        match = re.search(r'https?://\S+', first_line)
        if not match:
            raise ValueError("복사된 텍스트의 첫 줄에서 URL을 찾을 수 없습니다.")

        return {'url': match.group(0)}

    except Exception as e:
        # 오류 발생 시 스크린샷 저장 등 디버깅에 유용한 코드 추가 가능
        await page.screenshot(path="playwright_error_screenshot.png")
        raise e # 에러를 다시 발생시켜 consumer가 처리하도록 함

    finally:
        # 8. 작업 완료 후 컨텍스트를 닫아 모든 흔적(쿠키, 세션 등)을 제거
        await context.close()
