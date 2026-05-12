import time

from django.core.management.base import BaseCommand

from main.services.download_review_worker import run_worker_once


class Command(BaseCommand):
    help = "Run the download-review worker. Use --dry-run for simulated processing."

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
        once = options["once"]
        dry_run = options["dry_run"]
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
