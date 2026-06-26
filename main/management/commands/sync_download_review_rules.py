import sys
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand

from main.models import DownloadReviewRule
from main.views.review.ecm_rulebase import sync_rules_from_remote


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
        "원격 서버(DOWNLOAD_REVIEW_RULEBASE_SOURCE_URL)에서 점검규칙을 가져와 "
        "로컬 DB에 반영한다. 진단용으로 결과/오류를 자세히 출력한다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default=None,
            help="규칙 번들 URL. 생략하면 settings.DOWNLOAD_REVIEW_RULEBASE_SOURCE_URL 사용.",
        )

    def handle(self, *args, **options):
        _force_utf8_streams()

        url = options.get("url") or getattr(settings, "DOWNLOAD_REVIEW_RULEBASE_SOURCE_URL", "")
        self.stdout.write(f"DOWNLOAD_REVIEW_RULEBASE_SOURCE_URL = {url or '(미설정)'}")

        before = DownloadReviewRule.objects.filter(enabled=True).count()
        total = DownloadReviewRule.objects.count()
        self.stdout.write(f"동기화 전 로컬 규칙: 활성 {before}개 / 전체 {total}개")

        if not url:
            self.stderr.write(self.style.ERROR(
                "URL이 비어 있습니다. 워커를 띄운 셸에서 env.ps1이 로드됐는지, "
                "그리고 워커가 env 적용 후 재시작됐는지 확인하세요."
            ))
            return

        try:
            count = sync_rules_from_remote(url)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"동기화 실패: {exc}"))
            self.stderr.write(traceback.format_exc())
            return

        after = DownloadReviewRule.objects.filter(enabled=True).count()
        if count == 0:
            self.stdout.write(self.style.WARNING(
                "원격 서버 응답은 성공했지만 규칙이 0개입니다. "
                "원본 서버(194)에 활성화된 점검규칙이 실제로 등록돼 있는지 확인하세요."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"원격 규칙 {count}개 동기화 완료."))
        self.stdout.write(f"동기화 후 로컬 활성 규칙: {after}개")
