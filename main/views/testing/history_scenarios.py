from playwright.sync_api import Page, expect
import os, pathlib

LOGIN_URL = "http://210.104.181.10/auth/login/loginView.do"

# 계정 정보는 사용하지 않음 (로그인 제거)
LOGIN_ID = os.getenv("LOGIN_ID", "testingAI")
LOGIN_PW = os.getenv("LOGIN_PW", "12sqec34!")
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")

def run_scenario_sync(page: Page, job_dir: pathlib.Path, *, 시험번호: str, **kwargs) -> str:
    assert 시험번호, "시험번호가 비어 있습니다."

    # ── 0) 홈으로 진입 후 '검색 입력창'이 보일 때까지 대기 ────────────────
    page.goto(f"{BASE_ORIGIN}/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # 로그인 페이지로 리다이렉트되었는지 빠르게 감지
    if "login" in page.url.lower():
        page.fill("input[name='user_id']", LOGIN_ID)
        page.fill("input[name='password']", LOGIN_PW)
        page.locator("input[name='password']").press("Enter")

    # 검색 인풋 등장까지 대기 (최대 60초, 1회 재시도)
    search_input = page.locator("input.top-search2-input[name='q']")
    try:
        expect(search_input).to_be_visible(timeout=60000)
    except Exception:
        # 느린 초기 로딩/리다이렉트 대비 재시도
        page.reload(wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        expect(search_input).to_be_visible(timeout=30000)

    # ── 1) 검색 ───────────────────────────────────────────
    search_value = f"{시험번호} 시험성적서"
    print(f"[DEBUG] 검색값 = {search_value}")

    search_input.fill(search_value)
    search_btn = page.locator("div.top-search2-btn.hcursor")
    expect(search_btn).to_be_visible(timeout=10000)

    with page.expect_load_state("networkidle"):
        search_btn.click()

    # ── 2) 결과 필터링 ─────────────────────────────────────
    title_cards = page.locator("div.search_ftr_file_list_title.hcursor.ellipsis")
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

    # (선택) 클립보드 권한 선부여: 동일 컨텍스트에서 origin 지정
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_ORIGIN)
        # 팝업이 다른 경로일 수 있으므로 한번 더
        if popup.url:
            origin = popup.url.split("/", 3)[:3]  # scheme://host
            origin = "/".join(origin) + "/"
            page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
    except Exception:
        pass  # 권한 없는 환경이면 무시 (아래 readText에서 에러 처리)

    # ── 3) 새창에서 내부 URL 복사 ─────────────────────────
    copy_btn = popup.locator("div#prop-view-document-btn-url-copy.prop-view-file-btn-internal-urlcopy.hcursor")
    expect(copy_btn).to_be_visible(timeout=15000)
    copy_btn.click()

    # 클립보드 텍스트 읽기
    copied_text = popup.evaluate("navigator.clipboard.readText()")
    print(f"[DEBUG] 복사된 문장: {copied_text!r}")

    # 디버깅 아티팩트 저장
    (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")
    popup.screenshot(path=str(job_dir / "popup_done.png"), full_page=True)
    page.screenshot(path=str(job_dir / "list_done.png"), full_page=True)

    if not copied_text:
        raise RuntimeError("복사된 문장을 읽지 못했습니다. 권한/정책/요소 변동을 확인하세요.")

    return copied_text
