import asyncio
import re
import logging
from re import Pattern
from typing import Dict
from datetime import datetime  # ★ 스크린샷 시간 기록을 위해 추가
from playwright.async_api import Browser, Page, Locator, expect

# ★ Windows OS 클립보드 사용
try:
    import win32clipboard
    import win32con
except ImportError:  # pywin32가 없으면 나중에 런타임 에러로 알려주기 위함
    win32clipboard = None
    win32con = None

logger = logging.getLogger(__name__)

# ★ 대상 웹사이트의 시작 URL
ECM_BASE_URL = "http://210.104.181.10"

def _get_clipboard_text_sync() -> str:
    """
    동기 방식으로 Windows 클립보드의 유니코드 텍스트를 읽습니다.
    (async 코드에서 asyncio.to_thread로 감싸서 사용)
    """
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
    """
    비동기 코드에서 사용할 클립보드 읽기 함수.
    클립보드가 잠겨 있을 수 있으므로 약간 재시도합니다.
    """
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            return await asyncio.to_thread(_get_clipboard_text_sync)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(delay_sec)
    raise RuntimeError(f"클립보드 읽기 실패: {last_exc}")

async def _wait_clipboard_change(
    before: str,
    timeout_ms: int = 5000,
    interval_ms: int = 100,
) -> str:
    """
    기존 클립보드 내용(before)과 다른 텍스트가 들어올 때까지 대기합니다.
    timeout_ms 내에 변화가 없으면 빈 문자열을 반환합니다.
    """
    elapsed = 0
    while elapsed < timeout_ms:
        try:
            current = await _get_clipboard_text()
        except Exception as e:
            logger.warning("[TASK] 클립보드 읽기 중 예외 (무시하고 재시도): %s", e)
            current = ""

        if current and current != before:
            return current

        await asyncio.sleep(interval_ms / 1000.0)
        elapsed += interval_ms

    return ""

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
        "tree_appear": 5_000,
        "click": 5_000,
        "doc_list_appear": 5_000,
        "file_list_appear": 5_000, # ★ 파일 목록 대기용 타임아웃
        "row_expect": 5_000,
        "copy_wait": 5_000,
    }

    try:
        # Step 0 ~ 2: 페이지 이동 및 트리 메뉴 탐색 (기존과 동일)
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

        # Step 3: 문서 목록에서 대상 문서 클릭 (디버깅 로그 추가)
        # ▶ 스크린샷 기준 실제 DOM 속성명은 events="document-list-viewDocument-click"
        doc_list_selector = 'span[events="document-list-viewDocument-click"]'
        logger.warning("[TASK] Step3: 문서 목록 셀렉터 = %s", doc_list_selector)

        # 문서 목록 로딩 대기
        await page.wait_for_selector(doc_list_selector, timeout=TO["doc_list_appear"])

        doc_list = page.locator(doc_list_selector)
        total = await doc_list.count()
        logger.warning("[TASK] Step3: 전체 문서 span 개수 = %s", total)

        # 디버깅용: 전체 텍스트 확인
        try:
            texts = await doc_list.all_inner_texts()
            logger.warning("[TASK] Step3: 전체 span 텍스트 목록 = %s", texts)
        except Exception as ex:
            logger.warning("[TASK] Step3: all_inner_texts() 실패: %s", ex)

        logger.warning("[TASK] Step3: 시험번호 정규식 = %s", test_no_pattern.pattern)

        # 1차 필터: 시험번호 포함
        by_testno = doc_list.filter(has_text=test_no_pattern)
        cnt_by_testno = await by_testno.count()
        logger.warning("[TASK] Step3: 시험번호 포함 span 개수 = %s", cnt_by_testno)
        try:
            by_testno_texts = await by_testno.all_inner_texts()
            logger.warning("[TASK] Step3: 시험번호 포함 span 텍스트 = %s", by_testno_texts)
        except Exception as ex:
            logger.warning("[TASK] Step3: by_testno.all_inner_texts() 실패: %s", ex)

        # 2차 필터: '시험성적서' 우선
        logger.warning("[TASK] Step3: 문서 목록 필터링 (시험성적서 우선)")
        target_doc = by_testno.filter(has_text="시험성적서")

        clicked = False
        cnt_target = await target_doc.count()
        logger.warning("[TASK] Step3: 시험번호+시험성적서 매칭 개수 = %s", cnt_target)

        if cnt_target == 1:
            await target_doc.click(timeout=TO["click"])
            clicked = True
            logger.warning("[TASK] Step3: '시험성적서' 문서 클릭 완료")
        else:
            logger.warning(
                "[TASK] Step3: '시험성적서'가 정확히 1개가 아님(count=%s) → fallback 시도",
                cnt_target,
            )

        # fallback: 시험번호 포함 & '품질평가보고서' 제외
        if not clicked:
            logger.warning(
                "[TASK] Step3-fallback: '품질평가보고서' 제외, 시험번호 포함 대상 클릭 시도"
            )
            fallback_doc = by_testno.filter(has_not_text="품질평가보고서")
            cnt_fallback = await fallback_doc.count()
            logger.warning("[TASK] Step3-fallback: 후보 개수 = %s", cnt_fallback)
            try:
                fb_texts = await fallback_doc.all_inner_texts()
                logger.warning("[TASK] Step3-fallback: 후보 텍스트 = %s", fb_texts)
            except Exception as ex:
                logger.warning("[TASK] Step3-fallback: all_inner_texts() 실패: %s", ex)

            if cnt_fallback == 1:
                await fallback_doc.click(timeout=TO["click"])
                clicked = True
                logger.warning("[TASK] Step3-fallback: 대표 문서 클릭 완료")

        if not clicked:
            # 이 시점까지 온 경우, 위의 로그(전체 span, 필터 결과)로 왜 못 찾았는지 역추적 가능
            raise RuntimeError(
                f"문서 목록에서 '{test_no}'에 해당하는 정확한 대상을 찾지 못했습니다."
            )

        table_rows = page.locator("tr.prop-view-file-list-item")
        target_row = table_rows.filter(has_text=test_no_pattern).filter(has_text="시험성적서")
        logger.warning("[TASK] Step4: 파일 행 존재 확인 (시험성적서, 10s)")
        await expect(target_row).to_have_count(1, timeout=TO["row_expect"])
        checkbox = target_row.locator('input[type="checkbox"]')
        logger.warning("[TASK] Step4: 체크박스 체크")
        await checkbox.check(timeout=TO["click"])
        await _prime_copy_sniffer(page)
        last_seq_before = await page.evaluate("() => window.__copy_seq|0")
        
        # Step 5: URL 복사 버튼 클릭 (브라우저는 버튼 클릭까지만 ⇒ URL 문자열은 OS 클립보드에서 읽음)
        copy_btn_selector = "div#prop-view-document-btn-url-copy"
        logger.warning("[TASK] Step5: URL 복사 버튼 클릭 (OS 클립보드 방식) (%s)", copy_btn_selector)

        if win32clipboard is None or win32con is None:
            raise RuntimeError("pywin32(win32clipboard, win32con)가 설치되어 있지 않아 OS 클립보드를 사용할 수 없습니다.")

        # 클릭 전 클립보드 상태를 저장 (변화 감지를 위해)
        before_clip = ""
        try:
            before_clip = await _get_clipboard_text()
            logger.warning(
                "[TASK] Step5: 클릭 전 클립보드 텍스트 길이 = %s",
                len(before_clip or ""),
            )
        except Exception as e:
            logger.warning(
                "[TASK] Step5: 클릭 전 클립보드 읽기 실패 (무시하고 진행): %s",
                e,
            )

        copy_btn = page.locator(copy_btn_selector)
        btn_count = await copy_btn.count()
        logger.warning("[TASK] Step5: URL 복사 버튼 개수 = %s", btn_count)

        if btn_count == 0:
            raise RuntimeError("URL 복사 버튼을 찾지 못했습니다.")

        btn = copy_btn.first
        visible = await btn.is_visible()
        enabled = await btn.is_enabled()
        logger.warning(
            "[TASK] Step5: 버튼 상태 visible=%s, enabled=%s",
            visible,
            enabled,
        )

        try:
            await btn.click(timeout=TO["click"])
            logger.warning("[TASK] Step5: btn.click() 호출 완료 (예외 없음)")
        except Exception as e:
            logger.exception("[TASK] Step5: btn.click() 중 예외 발생: %s", e)
            raise

        # Step 6: OS 클립보드 내용이 변경될 때까지 대기
        logger.warning("[TASK] Step6: 클립보드 변화 대기 (최대 %dms)", TO["copy_wait"])
        pasted = await _wait_clipboard_change(before_clip, timeout_ms=TO["copy_wait"])
        logger.warning(
            "[TASK] Step6: 클립보드 변화 감지 후 텍스트 길이 = %s",
            len(pasted or ""),
        )

        if not pasted:
            raise RuntimeError("URL 복사 후 클립보드 텍스트를 확인하지 못했습니다. (타임아웃 또는 빈 값)")

        # 복사된 전체 문장에서 첫 줄만 사용 (메모장에 붙는 포맷 기준)
        first_line = pasted.splitlines()[0]
        m = re.search(r"(https?://\S+)", first_line)
        if not m:
            raise ValueError("클립보드 텍스트의 첫 줄에서 URL을 찾을 수 없습니다.")
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
