import sys
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

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
            "--source",
            default=None,
            help=(
                "Artifact source for --live runs: 'ecm' (default) or 'local'. "
                "'local' copies from LOCAL_ARTIFACT_SOURCE_ROOT instead of ECM "
                "(fake-live: full pipeline without ECM/Windows agent). "
                "Overrides settings.DOWNLOAD_REVIEW_SOURCE."
            ),
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
        source_name = options["source"]

        while True:
            # 장시간 실행되는 워커는 요청 사이클이 없어 Django가 DB 연결을 자동으로
            # 정리하지 않는다. 그러면 워커가 처음 연 reference(PostgreSQL) 연결을
            # 프로세스 수명 내내 재사용하게 되어, Django admin에서 점검규칙을 수정해도
            # 워커를 재시작하기 전까지는 예전 규칙으로 점검이 돌 수 있다.
            # 루프마다 오래된 연결을 닫아(다음 쿼리에서 새로 열림) 항상 최신 규칙을 읽게 한다.
            close_old_connections()

            result = run_worker_once(
                dry_run=dry_run,
                sleep_seconds=step_sleep,
                headless=headless,
                source_name=source_name,
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
