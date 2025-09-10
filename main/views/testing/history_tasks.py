import os, pathlib, traceback, asyncio, functools
from django.db import transaction
from django.utils import timezone
from playwright.sync_api import sync_playwright
from ...models import Job
from .history_scenarios import run_scenario_sync

RUNS_DIR = pathlib.Path(__file__).resolve().parent.parent / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

PW_CHANNEL  = os.getenv("PW_CHANNEL", "chrome")
PW_HEADLESS = os.getenv("PW_HEADLESS", "false").lower() == "true"
TIMEZONE_ID = os.getenv("PW_TZ", "Asia/Seoul")
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")

def _run_playwright_job_task_sync(job_id: str, data: dict):
    # ← 기존 run_playwright_job_task 본문을 이 함수로 그대로 옮기세요
    job_dir = RUNS_DIR / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    page = None
    try:
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job_id)
            job.status = "RUNNING"
            job.save(update_fields=["status", "updated_at"])

        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel=PW_CHANNEL,
                headless=PW_HEADLESS,
                args=["--disable-gpu", "--no-sandbox",
                      "--disable-features=IsolateOrigins,site-per-process"],
            )
            context = browser.new_context(
                accept_downloads=True,
                timezone_id=TIMEZONE_ID,
                locale="ko-KR",
            )
            # 권한은 HTTPS일 때만 시도
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

            (job_dir / "copied.txt").write_text(copied_text or "", encoding="utf-8")

            context.close()
            browser.close()

        Job.objects.filter(pk=job_id).update(
            status="DONE", final_link=copied_text, updated_at=timezone.now()
        )

    except Exception as e:
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
    Sync Playwright를 실행중 루프와 분리하기 위해 executor(별도 쓰레드)로 보냄.
    """
    loop = asyncio.get_running_loop()
    fn = functools.partial(_run_playwright_job_task_sync, job_id, data)
    return await loop.run_in_executor(None, fn)
