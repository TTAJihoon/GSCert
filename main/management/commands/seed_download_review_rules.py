from __future__ import annotations

import re
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import DownloadReviewRule, DownloadReviewRuleSeverity
from main.views.review.ecm_reference_db import ARTIFACT_REVIEW_COLUMNS


RULE_TYPE = "required_file_name_contains"
RULE_VERSION = "draft-1"


class Command(BaseCommand):
    help = "Seed draft download review inspection rules from artifact review columns."

    def add_arguments(self, parser):
        enabled_group = parser.add_mutually_exclusive_group()
        enabled_group.add_argument(
            "--enable",
            action="store_true",
            help="Enable seeded rules. Use only after confirming real file-name mappings.",
        )
        enabled_group.add_argument(
            "--disable",
            action="store_true",
            help="Disable seeded rules.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update names, config, ordering, and other non-enabled fields for existing rules.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the planned changes without writing to workflow.db.",
        )

    def handle(self, *args, **options):
        enabled_override = _enabled_override(options)
        specs = _rule_specs()
        db_alias = DownloadReviewRule.objects.db
        stats = {"created": 0, "updated": 0, "unchanged": 0}

        if options["dry_run"]:
            self._apply_specs(specs, options, enabled_override, stats, dry_run=True)
        else:
            with transaction.atomic(using=db_alias):
                self._apply_specs(specs, options, enabled_override, stats, dry_run=False)

        mode = "dry-run " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}download review rule seed complete: "
                f"created={stats['created']} updated={stats['updated']} unchanged={stats['unchanged']}"
            )
        )

    def _apply_specs(self, specs, options, enabled_override, stats, dry_run):
        for spec in specs:
            rule = DownloadReviewRule.objects.filter(code=spec["code"]).first()
            if rule is None:
                stats["created"] += 1
                if not dry_run:
                    create_data = dict(spec)
                    create_data["enabled"] = enabled_override if enabled_override is not None else False
                    DownloadReviewRule.objects.create(**create_data)
                continue

            update_data = {}
            if options["update_existing"]:
                for field_name, value in spec.items():
                    if getattr(rule, field_name) != value:
                        update_data[field_name] = value

            if enabled_override is not None and rule.enabled != enabled_override:
                update_data["enabled"] = enabled_override

            if update_data:
                stats["updated"] += 1
                if not dry_run:
                    for field_name, value in update_data.items():
                        setattr(rule, field_name, value)
                    rule.save(update_fields=[*update_data.keys(), "updated_at"])
            else:
                stats["unchanged"] += 1


def _enabled_override(options: dict[str, Any]) -> bool | None:
    if options["enable"]:
        return True
    if options["disable"]:
        return False
    return None


def _rule_specs():
    return [
        {
            "code": f"artifact_{index:02d}",
            "name": column_name,
            "target_file_pattern": "",
            "target_file_type": "pdf" if "PDF" in column_name.upper() else "any",
            "rule_type": RULE_TYPE,
            "config_json": {
                "contains": _default_keyword(column_name),
                "artifact_column": column_name,
            },
            "severity": DownloadReviewRuleSeverity.ERROR,
            "version": RULE_VERSION,
            "sort_order": index,
        }
        for index, column_name in enumerate(ARTIFACT_REVIEW_COLUMNS, start=1)
    ]


def _default_keyword(column_name: str) -> str:
    keyword = re.sub(r"\([^)]*\)", "", column_name).strip()
    return keyword or column_name
