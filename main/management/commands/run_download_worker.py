import sys
import time

from django.core.management.base import BaseCommand

from main.views.review.ecm_download_review_worker import run_worker_once


def _force_utf8_streams():
    """Windows 일부 로케일(cp1252 등)에서 stdout이 한글을 인코딩하지 못해
    UnicodeEncodeError로 워커 프로세스가 죽는 것을 방지한다.

    워커 메시지(진행상황/에러)에는 한글이 포함되므로, 콘솔 코드페이지와
    무관하게 출력 스트림을 UTF-8로 고정한다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass


class Command(BaseCommand):
    help = "Run the download-review worker. Defaults to dry-run unless --live is set."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one startable job and exit.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate project processing without ECM, Playwright, or zip downloads.",
        )
        parser.add_argument(
            "--live",
            action="store_true",
            help="Run real ECM/Windows agent automation. Use only on the agent PC.",
        )
        parser.add_argument(
            "--no-headless",
            action="store_true",
            help="Show the browser window (for development/debugging).",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=5.0,
            help="Seconds to wait between worker loop checks when --once is not set.",
        )
        parser.add_argument(
            "--step-sleep",
            type=float,
            default=0.0,
            help="Seconds to wait between dry-run project state transitions.",
        )

    def handle(self, *args, **options):
        _force_utf8_streams()
        once = options["once"]
        dry_run = options["dry_run"] or not options["live"]
        headless = not options["no_headless"]
        poll_interval = max(options["poll_interval"], 0.1)
        step_sleep = max(options["step_sleep"], 0.0)

        while True:
            result = run_worker_once(
                dry_run=dry_run,
                sleep_seconds=step_sleep,
                headless=headless,
            )
            if result.processed:
                self.stdout.write(
                    self.style.SUCCESS(f"{result.status}: {result.job_id} - {result.message}")
                )
            else:
                self.stdout.write(f"{result.status}: {result.message}")

            if once:
                return

            time.sleep(poll_interval)
