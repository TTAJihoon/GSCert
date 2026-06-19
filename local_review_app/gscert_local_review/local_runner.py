from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .document_reader import DocumentReadError, WordDocument, read_word_document
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
    if rule_type == "document_artifact_check":
        return _evaluate_document_artifact_rule(scan, rule, project_number)
    if rule_type == "rawdata_folder_structure_check":
        return _evaluate_rawdata_rule(scan, rule)
    if rule_type in DOCUMENT_RULE_TYPES:
        return _unsupported_result(rule, "이 규칙은 문서 내용 검사 엔진 연결 후 로컬 앱에서 지원됩니다.")
    return _unsupported_result(rule, f"아직 로컬 앱에서 지원하지 않는 규칙 유형입니다: {rule_type or '-'}")


def _evaluate_document_artifact_rule(scan: FolderScan, rule: dict[str, Any], project_number: str) -> LocalRuleResult:
    config = _config(rule)
    keywords = _keyword_list(config, rule, project_number)
    matched_files = _matching_files(scan.files, keywords, _extensions(config))
    required_result = _check_required_file_specs(config, matched_files)
    if not required_result["passed"]:
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=FAIL,
            expected=required_result["expected"],
            actual=required_result["actual"],
            message=str(config.get("missing_message") or "필요한 문서 파일을 찾지 못했습니다."),
        )

    supported_checks, unsupported_checks = _split_supported_content_checks(config.get("content_checks") or [])
    if not supported_checks and not unsupported_checks:
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=PASS,
            expected=required_result["expected"],
            actual=required_result["actual"],
            message=str(config.get("pass_message") or "필요한 문서 파일을 확인했습니다."),
        )

    documents: dict[str, WordDocument] = {}
    failures: list[dict[str, str]] = []
    for check in supported_checks:
        check_extensions = _extensions(check) or [".docx", ".docm"]
        candidates = [file for file in matched_files if file.extension.lower() in check_extensions]
        if not candidates:
            failures.append(
                {
                    "expected": "검사 대상 Word 파일",
                    "actual": "대상 파일 없음",
                    "message": str(check.get("failure_message") or "문서 내용 검사 대상 파일을 찾지 못했습니다."),
                }
            )
            continue
        file = candidates[0]
        try:
            document = documents.setdefault(file.relative_path, read_word_document(Path(scan.folder) / file.relative_path))
            result = _run_word_content_check(check, document, project_number)
        except DocumentReadError as exc:
            result = {
                "passed": False,
                "expected": "Word 파일 파싱 가능",
                "actual": str(exc),
                "message": str(exc),
            }
        if not result["passed"]:
            failures.append(result)

    first = matched_files[0] if matched_files else None
    if failures:
        first_failure = failures[0]
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=FAIL,
            expected=first_failure["expected"],
            actual=first_failure["actual"],
            message=first_failure["message"],
            file_path=first.relative_path if first else "",
            file_name=first.name if first else "",
        )
    if unsupported_checks:
        unsupported_types = ", ".join(sorted({str(check.get("type") or "-") for check in unsupported_checks}))
        return LocalRuleResult(
            rule_code=str(rule.get("code") or ""),
            rule_name=str(rule.get("name") or ""),
            status=UNSUPPORTED,
            expected="지원되는 Word 내용 검사",
            actual=f"미지원 검사 포함: {unsupported_types}",
            message="PDF 또는 아직 연결되지 않은 문서 내용 검사가 포함되어 프로그램 업데이트가 필요합니다.",
            file_path=first.relative_path if first else "",
            file_name=first.name if first else "",
        )
    return LocalRuleResult(
        rule_code=str(rule.get("code") or ""),
        rule_name=str(rule.get("name") or ""),
        status=PASS,
        expected=required_result["expected"],
        actual=required_result["actual"],
        message=str(config.get("pass_message") or "문서 파일과 Word 내용을 확인했습니다."),
        file_path=first.relative_path if first else "",
        file_name=first.name if first else "",
    )


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


def _check_required_file_specs(config: dict[str, Any], matched_files: list[FileRecord]) -> dict[str, Any]:
    specs = config.get("required_files") or []
    if not specs:
        exact_count = config.get("exact_count")
        min_count = int(config.get("min_count") or exact_count or 1)
        passed = len(matched_files) == int(exact_count) if exact_count is not None else len(matched_files) >= min_count
        return {
            "passed": passed,
            "expected": f"문서 파일 {exact_count}개" if exact_count is not None else f"문서 파일 {min_count}개 이상",
            "actual": _file_actual_text(matched_files),
        }

    expected_parts: list[str] = []
    actual_parts: list[str] = []
    all_passed = True
    for spec in specs:
        spec_config = spec if isinstance(spec, dict) else {}
        extensions = _extensions(spec_config)
        files = [file for file in matched_files if not extensions or file.extension.lower() in extensions]
        exact_count = spec_config.get("exact_count")
        min_count = int(spec_config.get("min_count") or exact_count or 1)
        if exact_count is not None:
            passed = len(files) == int(exact_count)
            expected_parts.append(f"{', '.join(extensions) or '문서'} {exact_count}개")
        else:
            passed = len(files) >= min_count
            expected_parts.append(f"{', '.join(extensions) or '문서'} {min_count}개 이상")
        all_passed = all_passed and passed
        actual_parts.append(f"{', '.join(extensions) or '문서'} {len(files)}개")
    return {
        "passed": all_passed,
        "expected": " / ".join(expected_parts),
        "actual": " / ".join(actual_parts),
    }


def _split_supported_content_checks(checks: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    supported_types = {
        "docx_table_next_cell_equals",
        "docx_text_contains",
        "docx_header_contains",
        "docx_footer_contains",
        "docx_next_paragraph_matches",
    }
    supported: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("type") or "") in supported_types:
            supported.append(check)
        else:
            unsupported.append(check)
    return supported, unsupported


def _run_word_content_check(check: dict[str, Any], document: WordDocument, project_number: str) -> dict[str, Any]:
    check_type = str(check.get("type") or "")
    if check_type == "docx_table_next_cell_equals":
        return _check_word_table_next_cell_equals(check, document, project_number)
    if check_type == "docx_text_contains":
        texts = [_resolve_text(text, project_number) for text in _string_list(check.get("texts") or check.get("text"))]
        actual_text = document.full_text
        passed = all(_contains_text(actual_text, text, check) for text in texts)
        return _content_result(
            check,
            passed,
            expected=", ".join(texts),
            actual="포함" if passed else "누락",
            default_message="문서에 필요한 문구가 없습니다.",
        )
    if check_type == "docx_header_contains":
        text = _resolve_text(str(check.get("text") or ""), project_number)
        passed = _contains_text(document.header_text, text, check)
        return _content_result(
            check,
            passed,
            expected=f"머리글에 {text} 포함",
            actual=document.header_text or "머리글 없음",
            default_message="머리글에 필요한 문구가 없습니다.",
        )
    if check_type == "docx_footer_contains":
        text = _resolve_text(str(check.get("text") or ""), project_number)
        passed = _contains_text(document.footer_text, text, check)
        return _content_result(
            check,
            passed,
            expected=f"바닥글에 {text} 포함",
            actual=document.footer_text or "바닥글 없음",
            default_message="바닥글에 필요한 문구가 없습니다.",
        )
    if check_type == "docx_next_paragraph_matches":
        return _check_word_next_paragraph_matches(check, document, project_number)
    return _content_result(
        check,
        False,
        expected=str(check.get("type") or "문서 검사"),
        actual="미지원",
        default_message="아직 지원하지 않는 문서 검사입니다.",
    )


def _check_word_table_next_cell_equals(check: dict[str, Any], document: WordDocument, project_number: str) -> dict[str, Any]:
    label = str(check.get("label") or "")
    expected_value = _resolve_text(str(check.get("expected") or ""), project_number)
    actual_value = ""
    for table in document.tables:
        for row in table:
            for index, cell in enumerate(row[:-1]):
                if _normalize_label(label) in _normalize_label(cell):
                    actual_value = row[index + 1]
                    break
            if actual_value:
                break
        if actual_value:
            break
    passed = _compare_text(actual_value, expected_value, check)
    return _content_result(
        check,
        passed,
        expected=f"{label} 오른쪽 셀 = {expected_value}",
        actual=f"{actual_value or '(없음)'}",
        default_message=f"{label} 값이 맞지 않습니다.",
    )


def _check_word_next_paragraph_matches(check: dict[str, Any], document: WordDocument, project_number: str) -> dict[str, Any]:
    after_texts = [_resolve_text(text, project_number) for text in _string_list(check.get("after_texts") or check.get("after_text"))]
    pattern = str(check.get("regex") or "")
    next_text = ""
    for index, paragraph in enumerate(document.paragraphs[:-1]):
        if all(_contains_text(paragraph, text, check) for text in after_texts):
            next_text = document.paragraphs[index + 1]
            break
    passed = bool(next_text) and bool(re.search(pattern, _normalize_for_compare(next_text, check)))
    return _content_result(
        check,
        passed,
        expected=f"다음 문단이 {pattern} 형식",
        actual=next_text or "다음 문단 없음",
        default_message="다음 문단 값이 형식과 맞지 않습니다.",
    )


def _content_result(
    check: dict[str, Any],
    passed: bool,
    *,
    expected: str,
    actual: str,
    default_message: str,
) -> dict[str, Any]:
    return {
        "passed": passed,
        "expected": expected,
        "actual": actual,
        "message": "" if passed else str(check.get("failure_message") or default_message),
    }


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


def _resolve_text(value: str, project_number: str) -> str:
    return str(value or "").replace("{project_number}", project_number).replace("{프로젝트번호}", project_number)


def _contains_text(actual: str, expected: str, check: dict[str, Any]) -> bool:
    return _normalize_for_compare(expected, check) in _normalize_for_compare(actual, check)


def _compare_text(actual: str, expected: str, check: dict[str, Any]) -> bool:
    return _normalize_for_compare(actual, check) == _normalize_for_compare(expected, check)


def _normalize_for_compare(value: str, check: dict[str, Any]) -> str:
    text = str(value or "")
    if check.get("remove_whitespace"):
        return _normalize(text)
    return " ".join(text.lower().split())


def _normalize_label(value: str) -> str:
    return _normalize(str(value or "").replace(":", "").replace("：", ""))


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
