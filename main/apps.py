# main/apps.py
from django.apps import AppConfig


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_auto_sync_rules_post_migrate, sender=self)


def _auto_sync_rules_post_migrate(sender, **kwargs):
    """migrate 완료 후 로컬 규칙이 없고 원격 URL이 설정되어 있으면 규칙을 자동 동기화한다.

    신규 서버 배포 시 `manage.py migrate`만 실행해도 규칙이 자동으로 채워진다.
    이미 규칙이 있으면 동기화를 건너뛴다.
    """
    from django.conf import settings
    remote_url = getattr(settings, "DOWNLOAD_REVIEW_RULEBASE_SOURCE_URL", "")
    if not remote_url:
        return
    try:
        from main.models import DownloadReviewRule
        if DownloadReviewRule.objects.exists():
            return
        from main.views.review.ecm_rulebase import sync_rules_from_remote
        count = sync_rules_from_remote(remote_url)
        print(f"[규칙 자동동기화] 원격 규칙 {count}개 가져옴 ({remote_url})")
    except Exception as exc:
        print(f"[규칙 자동동기화] 실패 (점검 실행 시 재시도): {exc}")
