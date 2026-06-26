from django.contrib import admin

from main.models import DownloadReviewRule


@admin.register(DownloadReviewRule)
class DownloadReviewRuleAdmin(admin.ModelAdmin):
    """점검규칙 관리(주 서버 PostgreSQL 단일 저장). 194/241 공용.

    규칙은 reference(PostgreSQL)에 저장되며 여기서 수정하면 두 서버에 즉시 반영된다.
    """
    list_display = ("sort_order", "code", "name", "rule_type", "severity", "enabled", "version", "updated_at")
    list_display_links = ("code", "name")
    list_filter = ("enabled", "severity", "rule_type", "version")
    list_editable = ("enabled", "sort_order")
    search_fields = ("code", "name", "rule_type", "target_file_pattern")
    ordering = ("sort_order", "name", "id")
    readonly_fields = ("id", "created_at", "updated_at")
    fields = (
        "id", "code", "name", "enabled", "sort_order",
        "rule_type", "target_file_type", "target_file_pattern",
        "severity", "version", "config_json",
        "created_at", "updated_at",
    )
