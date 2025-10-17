import re
import asyncio
import logging
from typing import Dict
from playwright.async_api import Browser, Page

logger = logging.getLogger(__name__)

# --- 날짜 파싱: yyyy.mm.dd 또는 yyyy-mm-dd 모두 허용 ---
def _get_date_parts(cert_date: str) -> tuple[str, str]:
    m = re.match(r'^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$', cert_date or '')
    if not m:
        raise ValueError(f"날짜 형식이 'yyyy.mm.dd' 또는 'yyyy-mm-dd'가 아닙니다. 입력값: {cert_date}")
    year, month, day = m.groups()
    return year, f"{year}{month.zfill(2)}{day.zfill(2)}"

# --- 복사 스니퍼: writeText/execCommand/copy 이벤트 가로채기 + 변화감지 ---
async def _prime_copy_sniffer(page: Page):
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
                if (e && e.clipboardData) {
                    txt = e.clipboardData.getData('text/plain') || '';
                }
                if (!txt && window.getSelection) {
                    txt = String(window.getSelection() || '');
                }
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

async def _wait_copied(page: Page, prev_seq: int, timeout_ms: int = 5000) -> str:
    elapsed = 0
    interval = 100
    while elapsed < timeout_ms:
        seq, txt = await page.evaluate("""() => [window.__copy_seq|0, String(window.__last_copied||'')]""")
        if seq > prev_seq and txt:
            return txt
        await page.wait_for_timeout(interval)
        elapsed += interval
    return ""

# --- 실제 작업 ---
async def run_playwright_task(browser: Browser, cert_date: str, test_no: str) -> Dict[str, str]:
    """
    필수 반환: {"url": "..."}
    예외 발생 시 consumer가 error로 내려줌.
    """
    year, yyyymmdd = _get_date_parts(cert_date)
    logger.warning("[TASK] 시작: cert_date=%s(%s), test_no=%s", cert_date, yyyymmdd, test_no)

    context = await browser.new_context()
    page = await context.new_page()
    try:
        # 1) ECM 진입 (필요한 URL로 교체)
        target_url = "https://ecm.example.com"  # TODO: 실제 시작 URL
        logger.warning("[TASK] Step1: goto %s", target_url)
        await page.goto(target_url, timeout=60_000)  # 60s

        # 2) 필요한 경우 로그인/탭 전환/검색 등 (선택자 교체)
        # logger.warning("[TASK] Step2: 로그인/탭 전환 등")
        # await page.locator("selector").fill("...")
        # await page.locator("button:has-text('로그인')").click()

        # 3) 프로젝트/문서 트리 이동 (연관 셀렉터로 교체)
        # logger.warning("[TASK] Step3: 문서 트리 이동")
        # await page.wait_for_selector("css=div#tree-panel", timeout=30_000)

        # 4) 복사 버튼 준비
        logger.warning("[TASK] Step4: 복사 스니퍼 설치")
        await _prime_copy_sniffer(page)
        prev_seq = await page.evaluate("() => window.__copy_seq|0")

        # 5) 'URL 복사' 버튼 클릭 (실제 셀렉터로 교체)
        copy_btn_selector = "div#prop-view-document-btn-url-copy"
        logger.warning("[TASK] Step5: 복사 버튼 클릭 (%s)", copy_btn_selector)
        await page.locator(copy_btn_selector).click(timeout=30_000)

        # 6) 복사 발생 대기 (최대 5s)
        logger.warning("[TASK] Step6: 복사 결과 대기")
        copied = await _wait_copied(page, prev_seq, timeout_ms=5_000)
        if not copied:
            raise RuntimeError("복사된 텍스트를 확인하지 못했습니다(타임아웃).")

        logger.warning("[TASK] 복사 완료: %s", copied[:120])

        # 7) 문자열에서 URL 추출 (정규식 예시, 필요 시 조정)
        m = re.search(r'(https?://\S+)', copied)
        if not m:
            raise RuntimeError("복사 텍스트에서 URL을 찾지 못했습니다.")
        url = m.group(1)

        logger.warning("[TASK] 완료 URL: %s", url)
        return {"url": url}

    finally:
        try:
            await context.close()
        except Exception as e:
            logger.exception("[TASK] context.close 실패: %s", e)
