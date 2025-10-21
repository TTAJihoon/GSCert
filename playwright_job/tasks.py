import asyncio
import re
import logging
from re import Pattern
from typing import Dict
from datetime import datetime  # ★ 스크린샷 시간 기록을 위해 추가
from playwright.async_api import Browser, Page, Locator, expect

logger = logging.getLogger(__name__)

# ★ 대상 웹사이트의 시작 URL
ECM_BASE_URL = "http://210.104.181.10"


# ---------- 유틸리티 함수 ----------

def _get_date_parts(cert_date: str) -> tuple[str, str]:
    """
    'yyyy.mm.dd' 또는 'yyyy-mm-dd' 형식의 날짜를 ('yyyy', 'yyyymmdd')로 분리합니다.
    """
    m = re.match(r'^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$', cert_date or '')
    if not m:
        raise ValueError(f"날짜 형식이 'yyyy.mm.dd' 또는 'yyyy-mm-dd'가 아닙니다. 입력값: {cert_date}")
    year, month, day = m.groups()
    return year, f"{year}{month.zfill(2)}{day.zfill(2)}"


def _testno_pat(test_no: str) -> Pattern:
    """
    시험번호의 구분자(하이픈/언더스코어)를 동일하게 취급하는 정규식을 생성합니다.
    """
    safe_no = re.escape(test_no).replace(r'\-', "[-_]")
    return re.compile(safe_no, re.IGNORECASE)


async def _prime_copy_sniffer(page: Page):
    """
    페이지 내에서 클립보드 복사 이벤트를 가로채기 위한 JavaScript를 주입합니다.
    """
    # ... (이 함수 내용은 변경 없음) ...
    inject_js = r"""
    (() => {
        if (window.__copy_sniffer_installed) return;
        window.__copy_sniffer_installed = true;
        window.__last_copied = '';
        window.__copy_seq = 0;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            const _origWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
            navigator.clipboard.writeText = async (t) => {
                try { window.__last_copied = String(t || ''); window.__copy_seq++; } catch(e) {}
                return _origWrite(t);
            };
        }
        document.addEventListener('copy', (e) => {
            try {
                let txt = '';
                if (e && e.clipboardData) { txt = e.clipboardData.getData('text/plain') || ''; }
                if (!txt && window.getSelection) { txt = String(window.getSelection() || ''); }
                if (txt) { window.__last_copied = String(txt); window.__copy_seq++; }
            } catch (err) {}
        }, true);
        const _origExec = document.execCommand ? document.execCommand.bind(document) : null;
        if (_origExec) {
            document.execCommand = function(command, ui, value) {
                try {
                    if ((command || '').toLowerCase() === 'copy') {
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
    JavaScript에 주입된 변수를 폴링하여 복사된 텍스트를 가져옵니다.
    """
    # ... (이 함수 내용은 변경 없음) ...
    interval = 100
    elapsed = 0
    while elapsed < timeout_ms:
        seq, txt = await page.evaluate("""() => [window.__copy_seq|0, String(window.__last_copied||'')]""")
        if seq > last_seq_before and txt:
            return txt
        await page.wait_for_timeout(interval)
        elapsed += interval
    return ""


# ---------- 메인 Playwright 작업 함수 ----------

# playwright_job/tasks.py 파일의 이 함수만 교체해주세요.

async def run_playwright_task(browser: Browser, cert_date: str, test_no: str) -> Dict[str, str]:
    """
    독립된 브라우저 컨텍스트를 생성하여 ECM 사이트 자동화 작업을 수행하고,
    결과 URL을 담은 딕셔너리를 반환합니다.
    """
    year, date_str = _get_date_parts(cert_date)
    test_no_pattern = _testno_pat(test_no)

    logger.warning("[TASK] 시작: cert_date=%s(%s), test_no=%s", cert_date, date_str, test_no)

    context = await browser.new_context()
    page = await context.new_page()

    TO = {
        "goto": 60_000,
        "tree_appear": 30_000,
        "click": 30_000,
        "doc_list_appear": 15_000,
        "file_list_appear": 15_000, # ★ 파일 목록 대기용 타임아웃
        "row_expect": 10_000,
        "copy_wait": 5_000,
    }

    try:
        # Step 0 ~ 2: 페이지 이동 및 트리 메뉴 탐색
        logger.warning("[TASK] Step0: goto %s", ECM_BASE_URL)
        resp = await page.goto(ECM_BASE_URL, timeout=TO["goto"], wait_until="domcontentloaded")
        logger.warning("[TASK] Step0: 응답 상태 = %s", resp.status if resp else None)
        html = await page.content()
        if "로그인" in html or "password" in html.lower():
            raise RuntimeError("ECM 로그인 페이지로 이동했습니다. 세션/인증이 필요합니다.")
        tree_selector = "div.edm-left-panel-menu-sub-item"
        logger.warning("[TASK] Step1: 트리 로딩 대기 (%s)", tree_selector)
        await page.wait_for_selector(tree_selector, timeout=TO["tree_appear"])
        tree = page.locator(tree_selector)
        logger.warning("[TASK] Step2-1: 연도 클릭 → %s", year)
        await tree.get_by_text(year).click(timeout=TO["click"])
        logger.warning("[TASK] Step2-2: 'GS인증심의위원회' 클릭")
        await tree.get_by_text("GS인증심의위원회").click(timeout=TO["click"])
        logger.warning("[TASK] Step2-3: 인증일자 클릭 → %s", date_str)
        await tree.get_by_text(date_str).click(timeout=TO["click"])
        logger.warning("[TASK] Step2-4: 시험번호 클릭 → %s", test_no)
        await tree.get_by_text(test_no).click(timeout=TO["click"])

        # ★★★★★★★★★★★★★★★★★★★★★ 1. 순서 바로잡기 ★★★★★★★★★★★★★★★★★★★
        # Step 2.5: '문서 목록'이 로딩될 때까지 기다립니다.
        doc_list_selector = 'span[event="document-list-viewDocument-click"]'
        logger.warning("[TASK] Step2.5: 문서 목록 로딩 대기...")
        await page.wait_for_selector(doc_list_selector, timeout=TO["doc_list_appear"])
        
        # Step 3: '문서 목록'에서 대상 문서를 클릭합니다.
        doc_list = page.locator(doc_list_selector)
        logger.warning("[TASK] Step3: 문서 목록 필터링 및 클릭")
        target_doc = doc_list.filter(has_text=test_no_pattern).filter(has_text="시험성적서")

        clicked = False
        if await target_doc.count() == 1:
            await target_doc.click(timeout=TO["click"])
            clicked = True
            logger.warning("[TASK] Step3: '시험성적서' 문서 클릭 완료")
        else:
            fallback_doc = doc_list.filter(has_text=test_no_pattern).filter(has_not_text="품질평가보고서")
            if await fallback_doc.count() == 1:
                await fallback_doc.click(timeout=TO["click"])
                clicked = True
                logger.warning("[TASK] Step3-fallback: 대표 문서 클릭 완료")

        if not clicked:
            raise RuntimeError(f"문서 목록에서 '{test_no}'에 해당하는 정확한 대상을 찾지 못했습니다.")

        # ★★★★★★★★★★★★★★★★★★★★★ 2. 새로운 대기 추가 ★★★★★★★★★★★★★★★★★★★
        # Step 3.5: 문서를 클릭했으니, 이제 '첨부 파일 목록'이 나타날 때까지 기다립니다.
        table_row_selector = "tr.prop-view-file-list-item"
        logger.warning("[TASK] Step3.5: 첨부 파일 목록 로딩 대기...")
        await page.wait_for_selector(table_row_selector, timeout=TO["file_list_appear"])


        # Step 4: '첨부 파일 목록'에서 대상 파일의 체크박스를 선택합니다.
        table_rows = page.locator(table_row_selector)
        target_row = table_rows.filter(has_text=test_no_pattern).filter(has_text="시험성적서")

        logger.warning("[TASK] Step4: 파일 행 존재 확인")
        await expect(target_row).to_have_count(1, timeout=TO["row_expect"])

        checkbox = target_row.locator('input[type="checkbox"]')
        logger.warning("[TASK] Step4: 체크박스 체크")
        await checkbox.check(timeout=TO["click"])

        # ... 이하 Step 5, 6, 7 및 나머지 코드는 모두 기존과 동일합니다 ...
        await _prime_copy_sniffer(page)
        last_seq_before = await page.evaluate("() => window.__copy_seq|0")
        copy_btn_selector = "div#prop-view-document-btn-url-copy"
        logger.warning("[TASK] Step5: URL 복사 버튼 클릭 (%s)", copy_btn_selector)
        await page.locator(copy_btn_selector).click(timeout=TO["click"])
        logger.warning("[TASK] Step6: 복사 결과 대기 (최대 %dms)", TO["copy_wait"])
        copied_text = await _get_sniffed_text(page, last_seq_before, timeout_ms=TO["copy_wait"])
        if not copied_text:
            raise RuntimeError("복사 이벤트를 확인하지 못했습니다. (타임아웃)")
        first_line = copied_text.splitlines()[0]
        m = re.search(r'(https?://\S+)', first_line)
        if not m:
            raise ValueError("복사된 텍스트의 첫 줄에서 URL을 찾을 수 없습니다.")
        url = m.group(1)
        logger.warning("[TASK] 완료 URL: %s", url)

        return {"url": url}

    except Exception as e:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"playwright_error_{timestamp}.png"
        await page.screenshot(path=screenshot_path)
        logger.warning(f"[TASK] 예외 발생, 스크린샷 저장({screenshot_path})")
        raise e

    finally:
        try:
            await context.close()
        except Exception as e:
            logger.exception("[TASK] context.close 실패: %s", e)
