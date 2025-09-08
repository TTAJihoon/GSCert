from playwright.sync_api import Page, expect
import os, pathlib

LOGIN_URL = "http://210.104.181.10/auth/login/loginView.do"

# 계정은 환경변수로도 오버라이드 가능 (하드코딩 최소화)
LOGIN_ID = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW = os.getenv("LOGIN_PW", "12sqec34!")
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")

def _safe_click_login(page: Page):
    """
    로그인 버튼이 명시되어 있지 않아, 일반적인 패턴으로 시도:
    1) submit 타입 버튼 클릭, 2) '로그인' 텍스트 버튼, 3) 비번 입력란에서 Enter
    """
    # 1) submit 류
    cand = page.locator("button[type='submit'], input[type='submit']")
    if cand.count() > 0:
        cand.first.click()
        return
    # 2) 텍스트 기반
    try:
        page.get_by_role("button", name="로그인").click()
        return
    except Exception:
        pass
    # 3) Enter
    page.locator("input[name='password']").press("Enter")

def run_scenario_sync(page: Page, job_dir: pathlib.Path, *, 시험번호: str, **kwargs) -> str:
    assert 시험번호, "시험번호가 비어 있습니다."

    # ── 1) 로그인 ──────────────────────────────────────────
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    expect(page.locator("input[name='user_id'].user-id.inputbox")).to_be_visible(timeout=15000)
    page.fill("input[name='user_id']", LOGIN_ID)
    page.fill("input[name='password']", LOGIN_PW)
    _safe_click_login(page)

    # 로그인 완료 대기: 검색창이 나타나는 것으로 판단
    page.wait_for_load_state("networkidle")
    # 검색 인풋 등장까지 대기
    search_input = page.locator("input.top-search2-input[name='q']")
    expect(search_input).to_be_visible(timeout=30000)

    # ── 2) 검색 ───────────────────────────────────────────
    search_value = f"{시험번호} 시험성적서"
    print(f"[DEBUG] 검색값 = {search_value}")

    search_input.fill(search_value)
    search_btn = page.locator("div.top-search2-btn.hcursor")
    expect(search_btn).to_be_visible(timeout=10000)

    with page.expect_load_state("networkidle"):
        search_btn.click()

    # ── 3) 결과 필터링 ─────────────────────────────────────
    title_cards = page.locator("div.search_ftr_file_list_title.hcursor.ellipsis")
    # 최소 1건 등장 대기
    expect(title_cards).to_be_visible(timeout=30000)

    count = title_cards.count()
    print(f"[DEBUG] 결과 항목 수: {count}")
    target_index = None
    sv_lower = search_value.lower()

    for i in range(count):
        txt = title_cards.nth(i).inner_text().strip()
        low = txt.lower()
        print(f"[DEBUG] [{i}] {txt}")
        if (sv_lower in low) and ("docx" in low):
            target_index = i
            print(f"[DEBUG] 매칭 성공 인덱스: {i}")
            break

    if target_index is None:
        raise RuntimeError("검색 결과에서 (검색값 & 'docx') 조건에 맞는 항목을 찾지 못했습니다.")

    # 상위 컨테이너 → 새창 버튼 클릭
    title_el = title_cards.nth(target_index)
    container = title_el.locator("xpath=ancestor::div[contains(@class,'search_ftr_file_cont')]")
    newwin_btn = container.locator("span.search_ftr_path_newwindow.hcursor[events='edm-document-property-view-newWindow-click']")

    with page.expect_popup() as popup_info:
        newwin_btn.click()
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded")
    popup.wait_for_load_state("networkidle")

    # ── 4) 새창에서 내부 URL 복사 ─────────────────────────
    copy_btn = popup.locator("div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor")
    expect(copy_btn).to_be_visible(timeout=15000)
    copy_btn.click()

    # 클립보드 텍스트 읽기(권한 필요)
    copied_text = popup.evaluate("navigator.clipboard.readText()")
    print(f"[DEBUG] 복사된 문장: {copied_text!r}")

    # 디버깅 아티팩트
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")
    popup.screenshot(path=str(job_dir / "popup_done.png"), full_page=True)
    page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)

    if not copied_text:
        raise RuntimeError("복사된 문장을 읽지 못했습니다. 권한/정책/요소 변동을 확인하세요.")

    return copied_text
