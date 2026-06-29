from __future__ import annotations

import re
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import DownloadReviewRule, DownloadReviewRuleSeverity
from main.rule_config_validation import validate_rule_spec
from main.views.review.ecm_reference_db import ARTIFACT_REVIEW_COLUMNS


DRAFT_RULE_TYPE = "required_file_name_contains"
DRAFT_RULE_VERSION = "draft-1"
ACTUAL_RULE_TYPE = "required_artifact_file"
ACTUAL_RULE_VERSION = "actual-1"
WORD_FILE_EXTENSIONS = [".docx", ".docm"]


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
        self._validate_specs(specs)
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

    def _validate_specs(self, specs):
        """DB 에 쓰기 전에 모든 spec 의 config_json 을 검증한다(dry-run 포함).

        하나라도 오류가 있으면 아무것도 쓰지 않고 중단한다 — 잘못된 config 가
        섞인 채로 일부만 반영되는 상황을 막는다.
        """
        all_errors = []
        for spec in specs:
            errors, warnings = validate_rule_spec(spec)
            all_errors.extend(errors)
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"warning: {warning}"))
        if all_errors:
            joined = "\n".join(f"  - {message}" for message in all_errors)
            raise CommandError(f"점검규칙 config 검증 실패 ({len(all_errors)}건):\n{joined}")

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
        "sort_order": _rule_sort_order(index, column_name),
    }


def _actual_rule_spec(index, column_name):
    common = {
        "code": f"artifact_{index:02d}",
        "name": column_name,
        "target_file_pattern": "",
        "rule_type": ACTUAL_RULE_TYPE,
        "severity": DownloadReviewRuleSeverity.ERROR,
        "version": ACTUAL_RULE_VERSION,
        "sort_order": _rule_sort_order(index, column_name),
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
                    {"extensions": WORD_FILE_EXTENSIONS, "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "content_checks": [
                    {
                        "type": "docx_table_next_cell_equals",
                        "extensions": WORD_FILE_EXTENSIONS,
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
                    {
                        "type": "docx_header_contains",
                        "extensions": WORD_FILE_EXTENSIONS,
                        "text": "{project_number}",
                        "failure_message": "합의서 머리말에 프로젝트 번호가 잘못 작성됨",
                    },
                    {
                        "type": "docx_footer_contains",
                        "extensions": WORD_FILE_EXTENSIONS,
                        "text": "TIS-0101-3 (00)",
                        "failure_message": "합의서 바닥글에 양식번호가 잘못 작성됨",
                    },
                ],
                "artifacts": [
                    {
                        "type": "pdf_first_page",
                        "extensions": [".pdf"],
                        "id": "pdf_first_page",
                        "label": "합의서 1페이지",
                    }
                ],
                "missing_message": "필요한 합의서 파일이 없습니다.",
                "pass_message": "합의서 Word/PDF와 시험신청번호를 확인했습니다.",
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
                "extensions": [".png", ".pptx"],
                "min_count": 1,
                "missing_message": "파일이 없습니다.",
                "pass_message": "시험환경구성도 파일을 확인했습니다.",
            },
        }
    if column_name == "품질특성별제품정보기재사항":
        title_terms = ["{project_number}", "품질특성별"]
        date_regex = (
            r"^\(?\s*(?:"
            r"\d{4}\s*[-./년]\s*\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?"
            r"|\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?"
            r")\s*\.?\s*\)?$"
        )
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "document_artifact_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["시험", "계획"],
                "filename_keywords": ["품질특성별", "{project_number}"],
                "required_files": [
                    {"extensions": WORD_FILE_EXTENSIONS, "exact_count": 1},
                ],
                "content_checks": [
                    {
                        "type": "docx_text_contains",
                        "extensions": WORD_FILE_EXTENSIONS,
                        "texts": title_terms,
                        "remove_whitespace": True,
                        "failure_message": "1페이지 제목에 프로젝트번호와 품질특성별 문구가 필요합니다.",
                    },
                    {
                        "type": "docx_next_paragraph_matches",
                        "extensions": WORD_FILE_EXTENSIONS,
                        "after_texts": title_terms,
                        "regex": date_regex,
                        "remove_whitespace": True,
                        "failure_message": "1페이지 날짜가 잘못되었습니다.",
                    },
                ],
                "missing_message": "파일명이 잘못되었습니다.",
                "pass_message": "품질특성별 문서의 프로젝트번호, 제목 문구, 날짜를 확인했습니다.",
            },
        }
    if column_name == "기능리스트":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "excel_feature_list_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["시험", "계획"],
                "filename_keywords": ["기능", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "exact_count": 1,
                "title_text": "{project_number} 기능리스트",
                "author_label": "작성자",
                "capture_anchor": "대분류",
                "missing_message": "파일이 없습니다.",
                "multiple_message": "기능리스트 파일이 여러개 존재함",
                "sheet_count_message": "불필요한 시트가 존재",
                "content_message": "시험번호 또는 작성자가 잘못 작성됨",
                "pass_message": "기능리스트를 확인했습니다.",
            },
        }
    if column_name == "시험계획서(PDF)":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "test_plan_document_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["시험", "계획"],
                "filename_keywords": ["계획서", "{project_number}"],
                "required_files": [
                    {"extensions": WORD_FILE_EXTENSIONS, "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "manager_expected": "김진영",
                "product_name_label": "소프트웨어 명",
                "version_label": "버전",
                "application_number_label": "시험신청번호",
                "configuration_marker": "5.1 형상항목 식별 규칙",
                "configuration_header": "형상항목 ID",
                "schedule_marker": "2.2 시험일정",
                "schedule_header": "WD",
                "footer_text": "Copyright {연도} TTA",
                "forbidden_footer_terms": [
                    {
                        "text": "TIS-",
                        "message": "시험계획서 바닥글에 양식번호가 잘못 작성됨",
                    },
                    {
                        "text": "소프트웨어시험인증연구소",
                        "message": "시험계획서 바닥글에 '소프트웨어시험인증연구소'라는 단어가 잘못 작성됨",
                    },
                ],
                "spec_marker": "<세부사양>",
                "report_spec_variable": "시험성적서_세부사양표",
                "pdf_artifact_label": "시험계획서 1페이지",
                "missing_message": "파일이 없습니다.",
                "date_message": "시험계획서 날짜가 잘못 작성됨",
                "manager_message": "시험계획서 담당자가 잘못 작성됨",
                "pl_message": "시험계획서 PL이 잘못 작성됨",
                "product_message": "제품정보가 틀림",
                "version_missing_message": "버전을 찾을 수 없음",
                "configuration_message": "형상항목 ID가 잘못 작성됨",
                "schedule_message": "시험일정 WD가 틀림",
                "footer_message": "바닥글 Copyright가 잘못 작성됨",
                "spec_message": "시험환경 세부사양 표가 결과서와 다름",
                "pass_message": "시험계획서를 확인했습니다.",
            },
        }
    if column_name == "최초/최종형상RawData":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "image_screenshot_folder_date_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["설계"],
                "min_images_per_folder": 5,
                "required_candidate_folder_count": 2,
                "folder_message": "제품 스크린샷 폴더를 찾을 수 없음",
                "date_message": "제품 스크린샷 생성일이 시험기간과 다름",
                "pass_message": "제품 스크린샷 rawdata를 확인했습니다.",
            },
        }
    if column_name == "테스트케이스":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "test_case_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["설계"],
                "filename_keywords": ["테스트케이스", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "exact_count": 1,
                "title_text": "{project_number} 테스트케이스",
                "author_label": "작성자:",
                "reviewer_label": "검토자:",
                "reviewer_expected": "김진영",
                "date_text": "작성일: {시작일} ~ {종료일}",
                "result_header": "상세 테스트 결과",
                "forbidden_footer_terms": [
                    {
                        "text": "소프트웨어시험인증연구소",
                        "message": "테스트케이스 바닥글에 '소프트웨어시험인증연구소'라는 단어가 잘못 작성됨",
                    },
                ],
                "missing_message": "파일이 존재하지 않음",
                "sheet_count_message": "테스트케이스 시트가 1개 이상임",
                "project_number_message": "프로젝트 번호가 잘못 작성됨",
                "author_message": "작성자 또는 검토자가 잘못 작성됨",
                "date_message": "작성일이 잘못 작성됨",
                "residual_message": "잔여 결함이 작성되지 않음",
                "pass_message": "테스트케이스를 확인했습니다.",
            },
        }
    if column_name == "결함리포트":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "defect_report_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["수행"],
                "filename_keywords": ["결함리포트", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "version_pattern": r"(?i)v(\d+)\.0",
                "count_mismatch_message": "시험성적서의 결함 차수와 결함리포트 개수가 다름",
                "forbidden_header_terms": [
                    {
                        "text": "프로젝트번호",
                        "message": "결함리포트 머리글에 프로젝트번호 삭제",
                    },
                ],
                "forbidden_footer_terms": [
                    {
                        "text": "소프트웨어시험인증연구소",
                        "message": "결함리포트 바닥글에 '소프트웨어시험인증연구소'라는 단어가 잘못 작성됨",
                    },
                ],
                "filename_message": "결함리포트 파일명이 잘못됨",
                "sheet_message": "{file_name}에 시트가 잘못 작성됨",
                "environment_message": "시험환경 정보 잘못 작성됨",
                "report_date_message": "프로젝트 번호, 결함 차시, 보고일자 중 잘못된 값이 작성됨",
                "pass_message": "결함리포트를 확인했습니다.",
            },
        }
    if column_name == "점검표(PDF)":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "inspection_checklist_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["설계"],
                "filename_keywords": ["점검표", "{project_number}"],
                "extensions": [".xlsx", ".xls", ".pdf"],
                "cover_sheet": "표지",
                "cover_author": "김진영",
                "feature_sheet": "기능별 점검표",
                "suitability_sheet": "2. 기능적합성",
                "reliability_sheet": "6. 신뢰성",
                "score_sheet": "측정항목별 점수표",
                "pdf_artifact_id": "pdf_first_page",
                "pdf_artifact_label": "점검표 1페이지",
                "forbidden_footer_terms": [
                    {
                        "text": "TIS-",
                        "message": "점검표 바닥글에 양식번호가 잘못 작성됨",
                    },
                ],
                "required_footer_terms": [
                    {
                        "text": "한국정보통신기술협회",
                        "message": "점검표 바닥글에 '한국정보통신기술협회'라는 단어가 누락됨",
                    },
                ],
                "missing_message": "파일이 존재하지 않음",
                "header_message": "머리글(프로젝트번호)이 잘못 작성됨",
                "cover_title_message": "표지 제목이 잘못 작성됨",
                "cover_date_message": "표지 날짜가 잘못 작성됨",
                "cover_author_message": "표지 작성자가 잘못 작성됨",
                "feature_blank_message": "기능별 점검표 시트에 빈 셀이 확인됨",
                "suitability_result_message": "기능적합성 시트의 기능표 결과값 미작성",
                "pdf_missing_message": "점검표 pdf 파일이 없음",
                "pass_message": "점검표를 확인했습니다.",
            },
        }
    if column_name == "1차/2차/성능/보안RawData":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "rawdata_folder_structure_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_checks": [
                    {
                        "keyword": "결함",
                        "failure_message": "결함리포트 rawdata 확인 불가",
                    },
                    {
                        "keyword": "보안",
                        "exact_child_folders": 2,
                        "each_child_has_entry": True,
                        "txt_only_pass": True,
                        "unwrap_single_folder": True,
                        "failure_message": "보안성 rawdata 확인 불가",
                    },
                    {
                        "keyword": "성능",
                        "min_entries": 1,
                        "failure_message": "성능 rawdata 확인 불가",
                    },
                ],
                "pass_message": "rawdata 폴더 구조를 확인했습니다.",
            },
        }
    if column_name == "시험성적서(PDF)":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "test_report_document_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["시험", "종료"],
                "filename_keywords": ["시험성적서", "{project_number}"],
                "required_files": [
                    {"extensions": WORD_FILE_EXTENSIONS, "exact_count": 1},
                    {"extensions": [".pdf"], "exact_count": 1},
                ],
                "spec_marker": "<세부사양>",
                "pdf_artifact_label": "시험성적서 1페이지",
                "missing_message": "파일이 없습니다.",
                "round_date_message": "결함리포트 송부 정보 확인 불가",
                "pass_message": "시험성적서를 확인했습니다.",
            },
        }
    if column_name == "시험기록서":
        return {
            **common,
            "target_file_type": "pdf",
            "rule_type": "downloadable_artifact_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": [],
                "filename_keywords": ["기록서"],
                "extensions": [".pdf"],
                "min_count": 1,
                "artifact_id": "test_record_pdf",
                "artifact_label": "시험기록서 1페이지",
                "artifact_first_page": True,
                "missing_message": "시험기록서 파일 확인 불가",
                "pass_message": "시험기록서 PDF 파일을 확인했습니다.",
            },
        }
    if column_name == "품질평가보고서":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "quality_evaluation_report_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["인증관련"],
                "filename_keywords": ["품질평가보고서", "{project_number}"],
                "extensions": WORD_FILE_EXTENSIONS,
                "exact_count": 1,
                "project_number_count": 6,
                "primary_signer": "성  명 : 김  성  희",
                "secondary_signer": "정  성  룡     (서명)",
                "company_label": "회사(기관)명",
                "quality_table_first_cell_keyword": "품질특성",
                "missing_message": "품질평가보고서 파일 확인 불가",
                "project_number_message": "프로젝트 번호 확인 필요",
                "signature_message": "서명란 이름 확인 필요",
                "company_message": "1. 신청 회사 현황 표 값 확인 필요",
                "request_date_message": "신청일자가 잘못 작성됨",
                "contract_date_message": "계약일자가 잘못 작성됨",
                "period_message": "시험기간이 잘못 작성됨",
                "committee_date_message": "인증위 날짜가 잘못 작성됨",
                "quality_value_message": "품질검사표의 품질부특성 측정값과 상이함",
                "na_message": "NA 해당사항 없음 작성 오류",
                "pass_message": "품질평가보고서를 확인했습니다.",
            },
        }
    if column_name == "품질검사표":
        return {
            **common,
            "target_file_type": "any",
            "rule_type": "quality_inspection_table_check",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["인증관련"],
                "filename_keywords": ["품질검사표", "{project_number}"],
                "extensions": [".xlsx", ".xls"],
                "sheet_name": "{project_number} 품질검사표",
                "quality_value_count": 33,
                "quality_value_excluded_indices": [27],
                "missing_message": "품질검사표 파일 확인 불가",
                "sheet_message": "품질검사표 시트명 확인 필요",
                "score_message": "측정항목별 점수표가 점검표와 상이함",
                "quality_value_message": "품질검사표의 품질부특성 측정값 확인 필요",
                "pass_message": "품질검사표를 확인했습니다.",
            },
        }
    if column_name == "SW저작권확인서":
        return {
            **common,
            "target_file_type": "pdf",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["인증관련"],
                "filename_keywords": ["확인서"],
                "extensions": [".pdf"],
                "min_count": 1,
                "missing_message": "저작권확인서 파일 누락",
                "pass_message": "저작권확인서 PDF 파일을 확인했습니다.",
            },
        }
    if column_name == "홍보이미지":
        return {
            **common,
            "target_file_type": "any",
            "config_json": {
                "artifact_column": column_name,
                "folder_keyword_chain": ["홍보"],
                "filename_keywords": [],
                "extensions": [],
                "min_count": 1,
                "forbidden_filename_keywords": ["예시"],
                "missing_message": "홍보자료 누락",
                "forbidden_message": "홍보이미지 파일명에 '예시'가 포함되어 있습니다.",
                "pass_message": "홍보이미지를 확인했습니다.",
            },
        }
    return None


def _rule_sort_order(index, column_name):
    if column_name == "시험성적서(PDF)":
        return 95
    if column_name == "시험계획서(PDF)":
        return 96
    if column_name == "테스트케이스":
        return 105
    if column_name == "품질검사표":
        return 145
    return index * 10


def _default_keyword(column_name: str) -> str:
    keyword = re.sub(r"\([^)]*\)", "", column_name).strip()
    return keyword or column_name
