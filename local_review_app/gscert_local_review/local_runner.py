from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if (_REPO_ROOT / "gscert_review_core").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gscert_review_core import engine
from gscert_review_core.types import ERROR, FAIL, PASS, UNSUPPORTED, RuleSpec

from .scanner import FolderScan


CORE_RULE_TYPES = {
    "min_file_count",
    "filename_contains_project_number",
    "required_extension",
    "required_file_name_contains",
    "required_artifact_file",
    "downloadable_artifact_check",
    "document_artifact_check",
    "all_files_non_empty",
    "excel_feature_list_check",
    "test_plan_document_check",
    "image_screenshot_folder_date_check",
    "test_case_check",
    "rawdata_folder_structure_check",
    "test_report_document_check",
    "defect_report_check",
    "inspection_checklist_check",
    "quality_inspection_table_check",
    "quality_evaluation_report_check",
}


@dataclass(frozen=True)
class LocalRuleResult:
    rule_code: str
    rule_name: str
    status: str
    expected: str
    actual: str
    message: str
    file_path: str = ""
    file_name: str = ""


@dataclass(frozen=True)
class LocalRunSummary:
    total_count: int
    passed_count: int
    failed_count: int
    unsupported_count: int
    error_count: int
    results: list[LocalRuleResult]


def run_cached_rules(
    scan: FolderScan,
    rule_bundle: dict[str, Any],
    project_number: str = "",
    metadata: Any | None = None,
) -> LocalRunSummary:
    """Run the cached server rulebase through the shared review engine."""

    context = _build_context(project_number, metadata)
    files = _engine_files(scan)
    rules = [_rule_spec(raw_rule) for raw_rule in rule_bundle.get("rules") or []]
    results: list[LocalRuleResult] = []

    for rule in rules:
        if rule.rule_type not in CORE_RULE_TYPES:
            results.append(
                LocalRuleResult(
                    rule_code=rule.code,
                    rule_name=rule.name,
                    status=UNSUPPORTED,
                    expected="공용 점검 엔진 지원",
                    actual="미지원",
                    message=f"아직 지원하지 않는 규칙 유형입니다: {rule.rule_type or '-'}",
                )
            )
            continue

        try:
            evaluations = engine.evaluate_rules([rule], context, files)
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            results.append(
                LocalRuleResult(
                    rule_code=rule.code,
                    rule_name=rule.name,
                    status=ERROR,
                    expected="공용 점검 엔진 실행",
                    actual="오류",
                    message=f"로컬 점검 중 오류가 발생했습니다: {exc}",
                )
            )
            continue

        if evaluations:
            results.append(_local_result(evaluations[0]))

    return LocalRunSummary(
        total_count=len(results),
        passed_count=sum(1 for result in results if result.status == PASS),
        failed_count=sum(1 for result in results if result.status == FAIL),
        unsupported_count=sum(1 for result in results if result.status == UNSUPPORTED),
        error_count=sum(1 for result in results if result.status == ERROR),
        results=results,
    )


def _rule_spec(rule: dict[str, Any]) -> RuleSpec:
    config = rule.get("config_json") or {}
    return RuleSpec(
        rule_type=str(rule.get("rule_type") or ""),
        code=str(rule.get("code") or ""),
        name=str(rule.get("name") or ""),
        config=config if isinstance(config, dict) else {},
        target_file_type=str(rule.get("target_file_type") or "any"),
        target_file_pattern=str(rule.get("target_file_pattern") or ""),
    )


def _engine_files(scan: FolderScan) -> list[engine.FileInfo]:
    root = Path(scan.folder)
    return [
        engine.FileInfo(
            name=file.name,
            path=str(root / file.relative_path),
            size=file.size_bytes,
            extension=file.extension,
        )
        for file in scan.files
    ]


def _build_context(project_number: str, metadata: Any | None):
    return engine.build_context(
        project_number=project_number or _meta(metadata, "project_number"),
        product_name=_meta(metadata, "product_name", "product"),
        company=_meta(metadata, "company_name", "company"),
        pl=_meta(metadata, "pl_name", "pl"),
        wd=_meta(metadata, "wd_name", "wd"),
        start_date=_meta(metadata, "start_date"),
        end_date=_meta(metadata, "end_date"),
        request_date=_meta(metadata, "request_date"),
        contract_date=_meta(metadata, "contract_date"),
        certification_committee_date=_meta(metadata, "cert_date", "certification_committee_date"),
    )


def _meta(source: Any | None, *names: str) -> str:
    if source is None:
        return ""
    for name in names:
        if isinstance(source, dict):
            value = source.get(name)
        else:
            value = getattr(source, name, None)
        if value:
            return str(value)
    return ""


def _local_result(evaluation: engine.RuleEvaluation) -> LocalRuleResult:
    return LocalRuleResult(
        rule_code=str(getattr(evaluation.rule, "code", "")),
        rule_name=str(getattr(evaluation.rule, "name", "")),
        status=evaluation.status,
        expected=str(evaluation.expected or ""),
        actual=str(evaluation.actual or ""),
        message=str(evaluation.message or ""),
        file_path=str(evaluation.file_path or ""),
        file_name=str(evaluation.file_name or ""),
    )
