import os, pathlib, traceback, re
from django.db import transaction
from django.utils import timezone
from playwright.sync_api import sync_playwright, expect, TimeoutError as PWTimeout
from ...models import Job
from .history_scenarios import run_scenario_sync

# ────────────────────────────────────────────────────────────
# 경로/환경
RUNS_DIR = pathlib.Path(__file__).resolve().parent.parent / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

AUTH_DIR = pathlib.Path(__file__).resolve().parent.parent / "auth_states"
AUTH_DIR.mkdir(parents=True, exist_ok=True)
USER_KEY = os.getenv("PW_STATE_USER", "shared")  # 사용자/계정 구분 키(동시 사용자면 키를 다르게)
AUTH_STATE_PATH = AUTH_DIR / f"{USER_KEY}.json"

PW_CHANNEL   = os.getenv("PW_CHANNEL", "chrome")                 # 실제 Chrome 사용
PW_HEADLESS  = os.getenv("PW_HEADLESS", "false").lower() == "true"
TIMEZONE_ID  = os.getenv("PW_TZ", "Asia/Seoul")
BASE_ORIGIN  = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL    = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")

UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# ────────────────────────────────────────────────────────────
# 헬퍼: 로그인 여부/부트스트랩/상태 확인

def _is_logged_in(page) -> bool:
    """URL이나 로그인 폼(#form-login) 존재 여부로 간단 판정"""
    if "/auth/login" in page.url.lower():
        return False
    try:
        return page.locator("#form-login").count() == 0
    except Exception:
        return True  # 페이지 구조가 달라도 폼이 없으면 로그인으로 간주

def _wait_login_completed(page, timeout=30000):
    page.wait_for_function(
        """
        () => {
          const notLoginURL = !/\\/auth\\/login/i.test(location.href);
          const form = document.querySelector('#form-login');
          const gone = !form || form.offsetParent === null || getComputedStyle(form).display === 'none';
          const bodyChanged = document.body && document.body.id !== 'login';
          return notLoginURL || gone || bodyChanged;
        }
        """,
        timeout=timeout,
    )

def _bootstrap_state(p):
    """
    상태 파일이 없거나 만료된 경우, 한 번 접속해서 세션 상태를 저장.
    - 에이전트가 자동 세션을 부여한다면 접속만으로 로그인됨
    - 아니라면 로그인 페이지에서 수동/자동 로그인 후 저장
    """
    browser = p.chromium.launch(
        channel=PW_CHANNEL,
        headless=False,  # 상태 발급은 headful 권장
        args=["--start-maximized", "--disable-gpu", "--no-sandbox"],
    )
    context = browser.new_context(
        user_agent=UA_CHROME,
        timezone_id=TIMEZONE_ID,
        locale="ko-KR",
    )
    page = context.new_page()

    # 1) 루트로 진입 → 에이전트가 세션을 부여한다면 여기서 곧바로 로그인 상태여야 함
    page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    if not _is_logged_in(page):
        # 2) 그래도 로그인 페이지면 한 번 더 명시 진입
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        # (선택) 환경변수로 아이디/패스워드가 제공되면 자동 로그인
        login_id = os.getenv("LOGIN_ID", "")
        login_pw = os.getenv("LOGIN_PW", "")
        if login_id and login_pw:
            try:
                user = page.locator("input[name='user_id']")
                pwd  = page.locator("input[name='password']")
                expect(user).to_be_visible(timeout=10000)
                expect(pwd).to_be_visible(timeout=10000)
                user.fill(login_id)
                pwd.fill(login_pw)

                login_btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
                expect(login_btn).to_be_visible(timeout=10000)
                try:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        login_btn.click()
                except PWTimeout:
                    login_btn.click()
                    page.wait_for_load_state("networkidle")
                _wait_login_completed(page, timeout=30000)
            except Exception:
                pass  # 자동 입력 실패 시, 에이전트/사람이 미리 로그인해둔 상태라면 다음 판정으로 넘어감

    # 최종 판정
    if not _is_logged_in(page):
        raise RuntimeError("세션 부트스트랩 실패: 에이전트/계정/도메인/정책을 확인하세요.")

    # 저장
    context.storage_state(path=str(AUTH_STATE_PATH))
    context.close(); browser.close()

def _ensure_valid_state(p):
    """AUTH_STATE_PATH가 없거나 만료면 새로 발급"""
    if not AUTH_STATE_PATH.exists():
        _bootstrap_state(p)
        return

    # 상태 파일 유효성 빠르게 확인
    browser = p.chromium.launch(
        channel=PW_CHANNEL,
        headless=True,
        args=["--disable-gpu", "--no-sandbox"],
    )
    context = browser.new_context(
        storage_state=str(AUTH_STATE_PATH),
        user_agent=UA_CHROME,
        timezone_id=TIMEZONE_ID,
        locale="ko-KR",
    )
    page = context.new_page()
    page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    ok = _is_logged_in(page)
    context.close(); browser.close()

    if not ok:
        _bootstrap_state(p)

# ────────────────────────────────────────────────────────────
# 메인 태스크

def run_playwright_job_task(job_id: str, data: dict):
    # 상태: RUNNING
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        job.status = "RUNNING"
        job.save(update_fields=["status", "updated_at"])

    job_dir = RUNS_DIR / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    page = None
    try:
        with sync_playwright() as pw:
            # 1) 세션 상태 확보/검증
            _ensure_valid_state(pw)

            # 2) 실제 잡 실행용 브라우저/컨텍스트 (동시 다중 사용자 OK: 컨텍스트 분리)
            browser = pw.chromium.launch(
                channel=PW_CHANNEL,
                headless=PW_HEADLESS,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            context = browser.new_context(
                storage_state=str(AUTH_STATE_PATH),  # ★ 세션 주입
                accept_downloads=True,
                timezone_id=TIMEZONE_ID,
                locale="ko-KR",
                user_agent=UA_CHROME,
            )

            # HTTP 환경에서 clipboard 권한은 종종 거절되므로, 실패는 무시
            try:
                if BASE_ORIGIN.lower().startswith("https://"):
                    context.grant_permissions(
                        permissions=["clipboard-read", "clipboard-write"],
                        origin=BASE_ORIGIN
                    )
            except Exception as pe:
                print("[WARN] grant_permissions 실패:", pe)

            page = context.new_page()

            # 프런트에서 넘어온 시험번호
            test_no = data.get("시험번호") or data.get("test_no") or ""
            copied_text = run_scenario_sync(page, job_dir, 시험번호=test_no)

            # 결과 저장(중복 저장이어도 무방)
            (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

            context.close()
            browser.close()

        Job.objects.filter(pk=job_id).update(
            status="DONE", final_link=copied_text, updated_at=timezone.now()
        )

    except Exception as e:
        # 실패 스크린샷
        try:
            if page:
                page.screenshot(path=str(job_dir / "error.png"), full_page=True)
        except Exception:
            pass
        Job.objects.filter(pk=job_id).update(
            status="ERROR",
            error=f"{e}\n{traceback.format_exc()}",
            updated_at=timezone.now(),
        )
