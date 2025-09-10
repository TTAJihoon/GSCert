# -*- coding: utf-8 -*-
"""
- Playwright Sync API를 항상 '별도 스레드'에서 돌려 asyncio 루프와 충돌하지 않도록 구성
- storage_state(auth_states/<USER_KEY>.json)로 세션 재사용 (에이전트가 로그인 유지 중인 환경 가정)
- 잡 산출물(job_dir): <프로젝트>/main/runs/<job_id>/ 하위에 저장
"""
import os
import re
import asyncio
import functools
import pathlib
import traceback
import threading

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
USER_KEY = os.getenv("PW_STATE_USER", "shared")  # 동시 다중 사용자면 계정/키를 다르게 주입
AUTH_STATE_PATH = AUTH_DIR / f"{USER_KEY}.json"

PW_CHANNEL  = os.getenv("PW_CHANNEL", "chrome")                 # 실제 Chrome
PW_HEADLESS = os.getenv("PW_HEADLESS", "false").lower() == "true"
TIMEZONE_ID = os.getenv("PW_TZ", "Asia/Seoul")
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")
LOGIN_URL   = os.getenv("LOGIN_URL", f"{BASE_ORIGIN}/auth/login/loginView.do")

UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# ────────────────────────────────────────────────────────────
# 로그인 상태 판정/대기

def _is_logged_in(page) -> bool:
    """URL/폼 존재 여부로 로그인 상태 간단 판정"""
    if "/auth/login" in page.url.lower():
        return False
    try:
        return page.locator("#form-login").count() == 0
    except Exception:
        return True

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

# ────────────────────────────────────────────────────────────
# 세션 상태 부트스트랩/검증 (Sync)

def _bootstrap_state():
    """상태가 없거나 만료 시 1회 접속해서 storage_state 저장"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=PW_CHANNEL, headless=False, args=["--start-maximized", "--disable-gpu", "--no-sandbox"]
        )
        context = browser.new_context(user_agent=UA_CHROME, timezone_id=TIMEZONE_ID, locale="ko-KR")
        page = context.new_page()

        # 에이전트가 세션을 부여할 루트로 접근
        page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        if not _is_logged_in(page):
            # 로그인 URL 재진입 (필요 시 자동 로그인)
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")

            login_id = os.getenv("LOGIN_ID", "")
            login_pw = os.getenv("LOGIN_PW", "")
            if login_id and login_pw:
                try:
                    user = page.locator("input[name='user_id']")
                    pwd  = page.locator("input[name='password']")
                    expect(user).to_be_visible(timeout=10000)
                    expect(pwd).to_be_visible(timeout=10000)
                    user.fill(login_id); pwd.fill(login_pw)
                    btn = page.locator('div[title="로그인"], div.area-right.btn-login.hcursor').first
                    expect(btn).to_be_visible(timeout=10000)
                    try:
                        with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                            btn.click()
                    except PWTimeout:
                        btn.click(); page.wait_for_load_state("networkidle")
                    _wait_login_completed(page, timeout=30000)
                except Exception:
                    pass

        if not _is_logged_in(page):
            context.close(); browser.close()
            raise RuntimeError("세션 부트스트랩 실패: 에이전트/계정/정책을 확인하세요.")

        context.storage_state(path=str(AUTH_STATE_PATH))
        context.close(); browser.close()

def _check_state_valid() -> bool:
    """storage_state가 유효한지 빠르게 확인"""
    if not AUTH_STATE_PATH.exists():
        return False
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=PW_CHANNEL, headless=True, args=["--disable-gpu", "--no-sandbox"])
        context = browser.new_context(
            storage_state=str(AUTH_STATE_PATH),
            user_agent=UA_CHROME, timezone_id=TIMEZONE_ID, locale="ko-KR",
        )
        page = context.new_page()
        page.goto(BASE_ORIGIN + "/", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        ok = _is_logged_in(page)
        context.close(); browser.close()
        return ok

def _ensure_valid_state():
    """없거나 만료면 새로 발급"""
    if not _check_state_valid():
        _bootstrap_state()

# ────────────────────────────────────────────────────────────
# 메인 태스크 (Sync 본체 + Async 래퍼)

def _run_playwright_job_task_sync(job_id: str, data: dict):
    """
    절대 async 컨텍스트에서 직접 호출하지 마십시오.
    async 컨텍스트에서는 아래 run_playwright_job_task(...)를 await 하세요.
    """
    # 가드: 현재 스레드에 이벤트 루프가 돌고 있으면 즉시 중단
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "Do NOT call _run_playwright_job_task_sync from an async context. "
            "Use: await run_playwright_job_task(job_id, data)"
        )
    except RuntimeError as _e:
        if "Do NOT call" in str(_e):
            raise
        # 정상 경로: 이 스레드에는 루프가 없음

    # 상태: RUNNING
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        job.status = "RUNNING"
        job.save(update_fields=["status", "updated_at"])

    job_dir = RUNS_DIR / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    page = None
    try:
        # 1) 세션 상태 확보
        _ensure_valid_state()

        # 2) 실제 잡 실행 (세션 주입)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                channel=PW_CHANNEL,
                headless=PW_HEADLESS,
                args=["--disable-gpu", "--no-sandbox",
                      "--disable-features=IsolateOrigins,site-per-process"],
            )
            context = browser.new_context(
                storage_state=str(AUTH_STATE_PATH),  # ★ 세션 재사용
                accept_downloads=True,
                timezone_id=TIMEZONE_ID,
                locale="ko-KR",
                user_agent=UA_CHROME,
            )

            # HTTP에서는 clipboard 권한이 거절될 수 있어 실패 무시
            try:
                if BASE_ORIGIN.lower().startswith("https://"):
                    context.grant_permissions(
                        permissions=["clipboard-read", "clipboard-write"],
                        origin=BASE_ORIGIN
                    )
            except Exception as pe:
                print("[WARN] grant_permissions 실패:", pe)

            page = context.new_page()

            test_no = data.get("시험번호") or data.get("test_no") or ""
            copied_text = run_scenario_sync(page, job_dir, 시험번호=test_no)

            # 결과 저장
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

def run_playwright_job_task_sync(job_id: str, data: dict):
    """동기 호출 환경(RQ 등)에서 사용"""
    return _run_playwright_job_task_sync(job_id, data)

async def run_playwright_job_task(job_id: str, data: dict):
    """
    비동기 호출 환경(ASGI/async view/Channels 등)에서 사용.
    Sync Playwright를 항상 '별도 스레드'에서 실행.
    """
    return await asyncio.to_thread(_run_playwright_job_task_sync, job_id, data)
