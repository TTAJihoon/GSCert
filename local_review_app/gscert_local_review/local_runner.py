from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .scanner import FileRecord, FolderScan


PASS = "pass"
FAIL = "fail"
UNSUPPORTED = "unsupported"
ERROR = "error"

SUPPORTED_FILE_RULE_TYPES = {
    "required_artifact_file",
    "required_file_name_contains",
    "downloadable_artifact_check",
}

DOCUMENT_RULE_TYPES = {
    "document_artifact_check",
    "excel_feature_list_check",
    "test_plan_document_check",
    "image_screenshot_folder_date_check",
    "test_case_check",
    "defect_report_check",
    "inspection_checklist_check",
    "test_report_document_check",
    "quality_evaluation_report_check",
    "quality_inspection_table_check",
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


def run_cached_rules(scan: FolderScan, rule_bundle: dict[str, Any], project_number: str = "") -> LocalRunSummary:
    results: list[LocalRuleResult] = []
    for rule in rule_bundle.get("rules") or []:
        try:
            results.append(_evaluate_rule(scan, rule, project_number))
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            results.append(
                LocalRuleResult(
                    rule_code=str(rule.get("code") or ""),
                    rule_name=str(rule.get("name") or ""),
                    status=ERROR,
                    expected="규칙 실행",
                    actual="오류",
                    message=f"로컬 점검 중 오류가 발생했습니다: {exc}",
                )
            )

    return LocalRunSummary(
        total_count=len(results),
        passed_count=sum(1 for result in results if result.status == PASS),
        failed_count=sum(1 for result in results if result.status == FAIL),
        unsupported_count=sum(1 for result in results if result.status == UNSUPPORTED),
        error_count=sum(1 for result in results if result.status == ERROR),
        results=results,
    )


def _evaluate_rule(scan: FolderScan, rule: dict[str, Any], project_number: str) -> LocalRuleResult:
    rule_type = str(rule.get("rule_type") or "")
    if rule_type in SUPPORTED_FILE_RULE_TYPES:
        return _evaluate_file_rule(scan, rule, project_number)
    if rule_type == "rawdata_folder_structure_check":
        return _evaluate_rawdata_rule(scan, rule)
    if rule_type in DOCUMENT_RULE_TYPES:
        return _unsupported_result(rule, "이 규칙은 문서 내용 검사 엔진 연결 후 로컬 앱에서 지원됩니다.")
    return _unsupported_result(rule, f"아직 로컬 앱에서 지원하지 않는 규칙 유형입니다: {rule_type or '-'}")


def _evaluate_file_rule(scan: FolderScan, rule: dict[str, Any], project_number: str) -> LocalRuleResult:
    config = _config(rule)
    keywords = _keyword_list(config, rule, project_number)
    extensions = _extensions(config)
    candidates = _matching_files(scan.files, keywords, extensions)
    min_count = int(config.get("min_count") or config.get("exact_count") or 1)
    exact_count = config.get("exact_count")
    forbidden_keywords = _string_list(config.get("forbidden_filename_keywords"))
    forbidden_matches = [
        file for file in candidates if any(keyword in _normalize(file.name) for keyword in forbidden_keywords)
    ]

    expected = _file_expected_text(keywords, extensions, exact_count, min_count, forbidden_keywords)
    actual = _file_actual_text(candidates)

    if forbidden_matches:
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=FAIL,
            expected=expected,
            actual=_file_actual_text(forbidden_matches),
            message=str(config.get("forbidden_message") or "제외해야 할 파일명이 포함되어 있습니다."),
            file_path=forbidden_matches[0].relative_path,
            file_name=forbidden_matches[0].name,
        )

    if exact_count is not None and len(candidates) != int(exact_count):
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=FAIL,
            expected=expected,
            actual=actual,
            message=str(config.get("missing_message") or f"조건에 맞는 파일이 {exact_count}개여야 합니다."),
        )

    if len(candidates) < min_count:
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=FAIL,
            expected=expected,
            actual=actual,
            message=str(config.get("missing_message") or "조건에 맞는 파일을 찾지 못했습니다."),
        )

    first = candidates[0] if candidates else None
    return LocalRuleResult(
        rule_code=str(rule.get("code") or ""),
        rule_name=str(rule.get("name") or ""),
        status=PASS,
        expected=expected,
        actual=actual,
        message=str(config.get("pass_message") or "조건에 맞는 파일을 확인했습니다."),
        file_path=first.relative_path if first else "",
        file_name=first.name if first else "",
    )


def _evaluate_rawdata_rule(scan: FolderScan, rule: dict[str, Any]) -> LocalRuleResult:
    config = _config(rule)
    failed_checks: list[str] = []
    passed_checks: list[str] = []
    rawdata_entries = [
        file.relative_path for file in scan.files if _contains_rawdata_label(file.relative_path)
    ] + [
        directory.relative_path
        for directory in scan.directories or []
        if _contains_rawdata_label(directory.relative_path)
    ]
    for check in config.get("folder_checks") or []:
        keyword = _normalize(str(check.get("keyword") or ""))
        if not keyword:
            continue
        matching_files = [file for file in scan.files if keyword in _normalize(file.relative_path)]
        matching_dirs = [
            directory
            for directory in scan.directories or []
            if keyword in _normalize(directory.relative_path)
        ]
        if matching_files or matching_dirs:
            passed_checks.append(str(check.get("keyword") or ""))
            continue
        failed_checks.append(str(check.get("failure_message") or check.get("keyword") or "rawdata"))

    expected = "rawdata 관련 폴더 또는 파일이 존재해야 합니다."
    actual_entries = passed_checks or rawdata_entries
    actual = ", ".join(actual_entries[:3]) if actual_entries else "조건에 맞는 rawdata 폴더/파일 없음"
    if len(actual_entries) > 3:
        actual += f" 외 {len(actual_entries) - 3}개"
    if not actual_entries:
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=FAIL,
            expected=expected,
            actual=actual,
            message="; ".join(failed_checks),
        )
    return LocalRuleResult(
        rule_code=str(rule.get("code") or ""),
        rule_name=str(rule.get("name") or ""),
        status=PASS,
        expected=expected,
        actual=actual,
        message=str(config.get("pass_message") or "rawdata 폴더 구조를 확인했습니다."),
    )


def _matching_files(files: list[FileRecord], keywords: list[str], extensions: list[str]) -> list[FileRecord]:
    matches: list[FileRecord] = []
    for file in files:
        normalized_path = _normalize(file.relative_path)
        if extensions and file.extension.lower() not in extensions:
            continue
        if keywords and not all(keyword in normalized_path for keyword in keywords):
            continue
        matches.append(file)
    return matches


def _keyword_list(config: dict[str, Any], rule: dict[str, Any], project_number: str) -> list[str]:
    raw_keywords: list[str] = []
    for key in ("filename_keywords", "file_name_keywords", "required_keywords", "keywords"):
        raw_keywords.extend(_string_list(config.get(key)))
    raw_keywords.extend(_string_list(config.get("contains")))
    if not raw_keywords:
        raw_keywords.extend(_string_list(config.get("artifact_column")))
    if not raw_keywords:
        raw_keywords.extend(_string_list(rule.get("name")))

    keywords = []
    for keyword in raw_keywords:
        value = keyword.replace("{project_number}", project_number).replace("{프로젝트번호}", project_number)
        normalized = _normalize(value)
        if normalized:
            keywords.append(normalized)
    return keywords


def _extensions(config: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("extensions", "allowed_extensions", "required_extensions", "file_extensions"):
        values.extend(_string_list(config.get(key)))
    return sorted({value.lower() if value.startswith(".") else f".{value.lower()}" for value in values if value})


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            if isinstance(item, (list, tuple, set)):
                items.extend(_string_list(item))
            elif item is not None:
                items.append(str(item))
        return items
    return [str(value)]


def _config(rule: dict[str, Any]) -> dict[str, Any]:
    config = rule.get("config_json") or {}
    return config if isinstance(config, dict) else {}


def _normalize(value: str) -> str:
    return "".join(value.lower().split())


def _contains_rawdata_label(value: str) -> bool:
    normalized = _normalize(value).replace("_", "").replace("-", "")
    return "rawdata" in normalized or "raw 데이터" in value.lower()


def _file_expected_text(
    keywords: list[str],
    extensions: list[str],
    exact_count: Any,
    min_count: int,
    forbidden_keywords: list[str],
) -> str:
    parts: list[str] = []
    if keywords:
        parts.append("파일명/경로 포함: " + ", ".join(keywords))
    if extensions:
        parts.append("확장자: " + ", ".join(extensions))
    if exact_count is not None:
        parts.append(f"개수: {exact_count}개")
    else:
        parts.append(f"개수: {min_count}개 이상")
    if forbidden_keywords:
        parts.append("제외 단어: " + ", ".join(forbidden_keywords))
    return " / ".join(parts)


def _file_actual_text(files: list[FileRecord]) -> str:
    if not files:
        return "조건에 맞는 파일 없음"
    if len(files) <= 3:
        return ", ".join(file.relative_path for file in files)
    return f"{', '.join(file.relative_path for file in files[:3])} 외 {len(files) - 3}개"


def _unsupported_result(rule: dict[str, Any], message: str) -> LocalRuleResult:
    return LocalRuleResult(
        rule_code=str(rule.get("code") or ""),
        rule_name=str(rule.get("name") or ""),
        status=UNSUPPORTED,
        expected="로컬 문서 검사 엔진 연결",
        actual="미지원",
        message=message,
    )
