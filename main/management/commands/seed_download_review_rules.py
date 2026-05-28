from __future__ import annotations

import re
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import DownloadReviewRule, DownloadReviewRuleSeverity
from main.views.review.ecm_reference_db import ARTIFACT_REVIEW_COLUMNS


DRAFT_RULE_TYPE = "required_file_name_contains"
DRAFT_RULE_VERSION = "draft-1"
ACTUAL_RULE_TYPE = "required_artifact_file"
ACTUAL_RULE_VERSION = "actual-1"


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
            "--only-real",
            action="store_true",
            help="Seed only implemented real rules instead of all artifact draft placeholders.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the planned changes without writing to workflow.db.",
        )

    def handle(self, *args, **options):
        enabled_override = _enabled_override(options)
        specs = _rule_specs(only_real=options["only_real"])
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


def _rule_specs(*, only_real=False):
    specs = [
        _actual_rule_spec(index, column_name) or _draft_rule_spec(index, column_name)
        for index, column_name in enumerate(ARTIFACT_REVIEW_COLUMNS, start=1)
    ]
    if only_real:
        return [spec for spec in specs if spec["version"] == ACTUAL_RULE_VERSION]
    return specs


def _draft_rule_spec(index, column_name):
    return {
        "code": f"artifact_{index:02d}",
        "name": column_name,
        "target_file_pattern": "",
        "target_file_type": "pdf" if "PDF" in column_name.upper() else "any",
        "rule_type": DRAFT_RULE_TYPE,
        "config_json": {
            "contains": _default_keyword(column_name),
            "artifact_column": column_name,
        },
        "severity": DownloadReviewRuleSeverity.ERROR,
        "version": DRAFT_RULE_VERSION,
        "sort_order": index,
    }


def _actual_rule_spec(index, column_name):
    common = {
        "code": f"artifact_{index:02d}",
        "name": column_name,
        "target_file_pattern": "",
        "rule_type": ACTUAL_RULE_TYPE,
        "severity": DownloadReviewRuleSeverity.ERROR,
        "version": ACTUAL_RULE_VERSION,
        "sort_order": index,
    }
    if column_name == "계약서":
        return {
            **common,
            "target_file_type": "pdf",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["계약"],
                "filename_keywords": ["계약서", "{project_number}"],
                "extensions": [".pdf"],
                "exact_count": 1,
                "missing_message": "파일이 없습니다.",
                "pass_message": "계약서 PDF 파일을 확인했습니다.",
            },
        }
    if column_name == "합의서(PDF)":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "document_artifact_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["계약"],
                "filename_keywords": ["합의서", "{project_number}"],
                "required_files": [
                    {"extensions": [".docx"], "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "content_checks": [
                    {
                        "type": "docx_table_next_cell_equals",
                        "extensions": [".docx"],
                        "label": "시험신청번호",
                        "expected": "{project_number}",
                        "failure_message": "프로젝트 번호가 맞지 않습니다.",
                    },
                    {
                        "type": "pdf_first_page_label_value_contains",
                        "extensions": [".pdf"],
                        "label": "시험신청번호",
                        "expected": "{project_number}",
                        "line_window": 3,
                        "failure_message": "프로젝트 번호가 맞지 않습니다.",
                    },
                ],
                "missing_message": "필요한 합의서 파일이 없습니다.",
                "pass_message": "합의서 docx/pdf와 시험신청번호를 확인했습니다.",
            },
        }
    if column_name == "수수료산정표":
        return {
            **common,
            "target_file_type": "xlsx",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["계약"],
                "filename_keywords": ["수수료산정표", "{project_number}"],
                "extensions": [".xlsx"],
                "exact_count": 1,
                "missing_message": "파일이 없습니다.",
                "pass_message": "수수료산정표 Excel 파일을 확인했습니다.",
            },
        }
    if column_name == "시험환경구성도":
        return {
            **common,
            "target_file_type": "any",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["시험", "계획"],
                "filename_keywords": ["구성도", "{project_number}"],
                "extensions": [],
                "exact_count": 1,
                "missing_message": "파일이 없습니다.",
                "multiple_message": "시험환경구성도 파일이 여러개 존재함",
                "pass_message": "시험환경구성도 파일을 확인했습니다.",
            },
        }
    if column_name == "품질특성별제품정보기재사항":
        title = "({project_number}) 품질특성별 시험대상제품 정보 기재사항"
        date_regex = (
            r"^\(?\s*(?:"
            r"\d{4}\s*[-./년]\s*\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?"
            r"|\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?"
            r")\s*\.?\s*\)?$"
        )
        return {
            **common,
            "target_file_type": "docx",
            "rule_type": "document_artifact_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["시험", "계획"],
                "filename_keywords": ["품질특성별", "{project_number}"],
                "required_files": [
                    {"extensions": [".docx"], "exact_count": 1},
                ],
                "content_checks": [
                    {
                        "type": "docx_text_contains",
                        "extensions": [".docx"],
                        "text": title,
                        "remove_whitespace": True,
                        "failure_message": "1페이지 제목이 잘못되었습니다.",
                    },
                    {
                        "type": "docx_next_paragraph_matches",
                        "extensions": [".docx"],
                        "after_text": title,
                        "regex": date_regex,
                        "remove_whitespace": True,
                        "failure_message": "1페이지 날짜가 잘못되었습니다.",
                    },
                ],
                "missing_message": "파일명이 잘못되었습니다.",
                "pass_message": "품질특성별 제품 정보 기재사항 제목과 날짜를 확인했습니다.",
            },
        }
    return None


def _default_keyword(column_name: str) -> str:
    keyword = re.sub(r"\([^)]*\)", "", column_name).strip()
    return keyword or column_name
