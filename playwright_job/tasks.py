import asyncio
import re
import logging
from re import Pattern
from typing import Dict
from playwright.async_api import Browser, Page, Locator, expect

logger = logging.getLogger(__name__)

ECM_BASE_URL = "http://210.104.181.10"  # ★ ECM 시작 URL (HTTP)


# ---------- 유틸 ----------

def _get_date_parts(cert_date: str) -> tuple[str, str]:
    """
    'yyyy.mm.dd' 또는 'yyyy-mm-dd' 형식의 날짜를
    ('yyyy', 'yyyymmdd')로 분리
    """
    m = re.match(r'^\s*(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})\s*$', cert_date or '')
    if not m:
        raise ValueError(f"날짜 형식이 'yyyy.mm.dd' 또는 'yyyy-mm-dd'가 아닙니다. 입력값: {cert_date}")
    year, month, day = m.groups()
    return year, f"{year}{month.zfill(2)}{day.zfill(2)}"


def _testno_pat(test_no: str) -> Pattern:
    """
    시험번호의 구분자(하이픈/언더스코어)를 동일하게 취급하는 정규식 생성.
    예: GS-B-24-0215 == GS_B_24_0215
    """
    safe_no = re.escape(test_no).replace(r'\-', "[-_]")
    return re.compile(safe_no, re.IGNORECASE)


async def _prime_copy_sniffer(page: Page):
    """
    클립보드 복사 파이프라인을 페이지 내부에서 가로챔:
    - navigator.clipboard.writeText
    - document 'copy' 캡처 이벤트
    - document.execCommand('copy') 래핑
    """
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


async def _get_sniffed_text(page: Page, last_seq_before: int, timeout_ms: int = 5000) -> str:
    """
    __copy_seq 증가(새 복사 발생)까지 폴링. 발생 시 __last_copied 반환.
    """
    interval = 100
    elapsed = 0
    while elapsed < timeout_ms:
        seq, txt = await page.evaluate("""() => [window.__copy_seq|0, String(window.__last_copied||'')]""")
        if seq > last_seq_before and txt:
            return txt
        await page.wait_for_timeout(interval)
        elapsed += interval
    return ""


# ---------- 메인 작업 ----------

async def run_playwright_task(browser: Browser, cert_date: str, test_no: str) -> Dict[str, str]:
    """
    ECM 홈으로 이동 → 트리/문서 탐색 → 체크박스 → URL 복사 → {"url": "..."} 반환.
    각 단계에 타임아웃/로그를 넣어 '어디서 멈췄는지'를 바로 파악 가능하게 함.
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
        "row_expect": 10_000,
        "copy_wait": 5_000,
    }

    try:
        # 0) ECM 홈으로 이동 (★ 추가됨)
        logger.warning("[TASK] Step0: goto %s", ECM_BASE_URL)
        resp = await page.goto(ECM_BASE_URL, timeout=TO["goto"], wait_until="domcontentloaded")
        try:
            status = resp.status if resp else None
            logger.warning("[TASK] Step0: 응답 상태 = %s", status)
        except Exception:
            pass

        # 간단한 로그인 감지(필요시 구체화)
        html = await page.content()
        if "로그인" in html or "password" in html.lower():
            raise RuntimeError("ECM 로그인 페이지로 이동했습니다. 세션/인증이 필요합니다.")

        # 1) 왼쪽 트리 패널 준비
        tree_selector = "div.edm-left-panel-menu-sub-item"
        logger.warning("[TASK] Step1: 트리 로딩 대기 (%s)", tree_selector)
        await page.wait_for_selector(tree_selector, timeout=TO["tree_appear"])

        # 2) 연도/조직/날짜/시험번호 클릭
        tree = page.locator(tree_selector)

        logger.warning("[TASK] Step2-1: 연도 클릭 → %s", year)
        await tree.get_by_text(year, exact=True).click(timeout=TO["click"])

        logger.warning("[TASK] Step2-2: 'GS인증심의위원회' 클릭")
        await tree.get_by_text("GS인증심의위원회", exact=True).click(timeout=TO["click"])

        logger.warning("[TASK] Step2-3: 인증일자 클릭 → %s", date_str)
        await tree.get_by_text(date_str, exact=True).click(timeout=TO["click"])

        logger.warning("[TASK] Step2-4: 시험번호 클릭 → %s", test_no)
        await tree.get_by_text(test_no, exact=True).click(timeout=TO["click"])

        # 3) 문서 목록에서 대상 문서 선택
        doc_list_selector = 'span[event="document-list-viewDocument-click"]'
        doc_list = page.locator(doc_list_selector)
        logger.warning("[TASK] Step3: 문서 목록 필터링 (시험성적서 우선)")
        target_doc = doc_list.filter(has_text=test_no_pattern).filter(has_text="시험성적서")

        clicked = False
        cnt = await target_doc.count()
        if cnt == 1:
            await target_doc.click(timeout=TO["click"])
            clicked = True
            logger.warning("[TASK] Step3: '시험성적서' 문서 클릭 완료")
        else:
            logger.warning("[TASK] Step3: 정확히 1개가 아님(count=%s) → fallback 시도", cnt)

        if not clicked:
            logger.warning("[TASK] Step3-fallback: '품질평가보고서' 제외, 시험번호 포함 대상 클릭")
            fallback_doc = doc_list.filter(has_text=test_no_pattern).filter(has_not_text="품질평가보고서")
            if await fallback_doc.count() == 1:
                await fallback_doc.click(timeout=TO["click"])
                clicked = True
                logger.warning("[TASK] Step3-fallback: 대표 문서 클릭 완료")

        if not clicked:
            raise RuntimeError(f"문서 목록에서 '{test_no}'에 해당하는 정확한 대상을 찾지 못했습니다.")

        # 4) 파일 목록에서 행/체크박스 선택
        table_rows = page.locator("tr.prop-view-file-list-item")
        target_row = table_rows.filter(has_text=test_no_pattern).filter(has_text="시험성적서")

        logger.warning("[TASK] Step4: 파일 행 존재 확인 (시험성적서, 10s)")
        await expect(target_row).to_have_count(1, timeout=TO["row_expect"])

        checkbox = target_row.locator('input[type="checkbox"]')
        logger.warning("[TASK] Step4: 체크박스 체크")
        await checkbox.check(timeout=TO["click"])

        # 5) 복사 스니퍼 설치 + URL 복사 버튼 클릭
        await _prime_copy_sniffer(page)
        last_seq_before = await page.evaluate("() => window.__copy_seq|0")

        copy_btn_selector = "div#prop-view-document-btn-url-copy"
        logger.warning("[TASK] Step5: URL 복사 버튼 클릭 (%s)", copy_btn_selector)
        await page.locator(copy_btn_selector).click(timeout=TO["click"])

        # 6) 복사 결과 대기
        logger.warning("[TASK] Step6: 복사 결과 대기 (최대 %dms)", TO["copy_wait"])
        copied_text = await _get_sniffed_text(page, last_seq_before, timeout_ms=TO["copy_wait"])
        if not copied_text:
            raise RuntimeError("복사 이벤트를 확인하지 못했습니다. (타임아웃)")

        # 7) 복사 텍스트에서 URL 추출
        first_line = copied_text.splitlines()[0]
        m = re.search(r'https?://\S+', first_line)
        if not m:
            raise ValueError("복사된 텍스트의 첫 줄에서 URL을 찾을 수 없습니다.")
        url = m.group(1)
        logger.warning("[TASK] 완료 URL: %s", url)

        return {"url": url}

    except Exception as e:
        # 디버깅을 위해 스크린샷 남김
        try:
            await page.screenshot(path="playwright_error_screenshot.png")
            logger.warning("[TASK] 예외 발생, 스크린샷 저장(playwright_error_screenshot.png)")
        except Exception:
            pass
        raise e

    finally:
        try:
            await context.close()
        except Exception as e:
            logger.exception("[TASK] context.close 실패: %s", e)
