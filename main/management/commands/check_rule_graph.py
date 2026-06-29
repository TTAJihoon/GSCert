from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from main.models import DownloadReviewRule
from main.rule_config_validation import _graph_entry, validate_rule_graph


class Command(BaseCommand):
    help = (
        "현재 DB(reference)의 *활성* 점검규칙 requires/produces 의존 그래프를 검증한다. "
        "운영자가 Admin 에서 sort_order 를 바꾸거나 규칙을 비활성화해 실행 순서가 "
        "깨졌는지(후속 규칙이 빈 산출 변수를 받게 되는지) 사전에 확인하는 용도."
    )

    def handle(self, *args, **options):
        rules = list(
            DownloadReviewRule.objects.filter(enabled=True).order_by("sort_order", "name", "id")
        )
        entries = [
            _graph_entry(rule.code, rule.name, rule.sort_order, rule.config_json)
            for rule in rules
        ]
        errors, warnings = validate_rule_graph(entries)

        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"warning: {warning}"))

        if errors:
            joined = "\n".join(f"  - {message}" for message in errors)
            raise CommandError(
                f"활성 규칙 {len(rules)}개 의존 그래프 검증 실패 ({len(errors)}건):\n{joined}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"활성 규칙 {len(rules)}개 의존 그래프 검증 통과"
                f"{f' (경고 {len(warnings)}건)' if warnings else ''}."
            )
        )
