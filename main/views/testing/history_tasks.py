import os, pathlib, traceback
from django.db import transaction
from django.utils import timezone
from playwright.sync_api import sync_playwright
from ...models import Job
from .history_scenarios import run_scenario_sync

RUNS_DIR = pathlib.Path(__file__).resolve().parent.parent / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

PW_CHANNEL = os.getenv("PW_CHANNEL", "chrome")          # 실제 Chrome 사용
PW_HEADLESS = os.getenv("PW_HEADLESS", "false").lower() == "true"
TIMEZONE_ID = os.getenv("PW_TZ", "Asia/Seoul")
BASE_ORIGIN = os.getenv("BASE_ORIGIN", "http://210.104.181.10")  # 동일 도메인 권한

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
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel=PW_CHANNEL,
                headless=PW_HEADLESS,   # 에이전트/보안 요구 시 headful 권장(False)
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            context = browser.new_context(
                accept_downloads=True,
                timezone_id=TIMEZONE_ID,
                locale="ko-KR",
            )
            # 클립보드 권한
            try:
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

            # 복사된 문장 디버깅 저장
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
