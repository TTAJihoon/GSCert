import sys

from django.core.management.base import BaseCommand

from main.views.review.ecm_download_review_jobs import force_stop_download_review_jobs


def _force_utf8_streams():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass


class Command(BaseCommand):
    help = (
        "진행중(RUNNING 포함) 다운로드 점검 작업을 강제 종료하고 워커 락을 해제한다. "
        "워커 비정상 종료로 작업이 멈춰 새 작업을 시작할 수 없을 때 사용한다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--job-id",
            default=None,
            help="특정 작업만 종료한다. 생략하면 활성(예약/대기/실행중) 작업 전체를 종료한다.",
        )

    def handle(self, *args, **options):
        _force_utf8_streams()
        job_id = options.get("job_id")
        result = force_stop_download_review_jobs(job_id)
        self.stdout.write(self.style.SUCCESS(result["message"]))
        self.stdout.write(
            f"강제 종료된 작업 수: {result['stopped_count']}, "
            f"락 해제: {'예' if result['lock_released'] else '아니오'}"
        )
