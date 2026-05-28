import fnmatch
import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.utils import timezone
from lxml import etree

from main.models import (
    DownloadReviewProjectReviewStatus,
    DownloadReviewRule,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
)
from main.views.review.ecm_download_verify import FileInfo
from main.views.review.ecm_reference_db import ARTIFACT_REVIEW_COLUMNS


class DownloadReviewInspectionError(RuntimeError):
    """검사 규칙을 실행할 수 없을 때 발생한다."""


class DownloadReviewCleanupSafetyError(RuntimeError):
    """다운로드 폴더 삭제 대상이 안전하지 않을 때 발생한다."""


@dataclass(frozen=True)
class RuleEvaluation:
    rule: DownloadReviewRule
    sequence: int
    status: str
    expected: str
    actual: str
    message: str
    file_path: str = ""
    file_name: str = ""
    raw_detail: dict | None = None


@dataclass(frozen=True)
class InspectionOutcome:
    project_review_status: str
    reference_review: str
    artifact_results: dict
    passed_count: int
    failed_count: int
    result_count: int


@dataclass(frozen=True)
class CleanupOutcome:
    deleted: bool
    message: str
    file_count: int = 0


def run_download_inspection(project, verify_result, file_summary) -> InspectionOutcome:
    """등록된 활성 규칙을 실행하고 규칙별 결과를 저장한다.

    실제 규칙은 DB의 inspection_rule에 등록된 항목을 기준으로 한다. 이 함수는 규칙을
    미리 생성하지 않으며, 규칙이 없으면 설정 오류로 처리한다.
    """
    rules = list(DownloadReviewRule.objects.filter(enabled=True).order_by("sort_order", "name", "id"))
    if not rules:
        raise DownloadReviewInspectionError("활성화된 점검규칙이 없습니다.")

    evaluations = [
        _evaluate_rule(rule, sequence, project, verify_result, file_summary)
        for sequence, rule in enumerate(rules, start=1)
    ]

    DownloadReviewRuleResult.objects.filter(job_project=project).delete()
    DownloadReviewRuleResult.objects.bulk_create(
        [
            DownloadReviewRuleResult(
                job_project=project,
                rule=evaluation.rule,
                rule_code=evaluation.rule.code,
                rule_name=evaluation.rule.name,
                sequence=evaluation.sequence,
                file_path=evaluation.file_path,
                file_name=evaluation.file_name,
                status=evaluation.status,
                expected=evaluation.expected,
                actual=evaluation.actual,
                message=evaluation.message,
                raw_detail_json=evaluation.raw_detail or {},
            )
            for evaluation in evaluations
        ]
    )

    failed_count = sum(
        1
        for evaluation in evaluations
        if evaluation.status in (DownloadReviewRuleStatus.FAIL, DownloadReviewRuleStatus.ERROR)
    )
    passed_count = len(evaluations) - failed_count
    artifact_results = _artifact_results_from_evaluations(evaluations)

    if failed_count:
        return InspectionOutcome(
            project_review_status=DownloadReviewProjectReviewStatus.NEEDS_FIX,
            reference_review="X",
            artifact_results=artifact_results,
            passed_count=passed_count,
            failed_count=failed_count,
            result_count=len(evaluations),
        )

    return InspectionOutcome(
        project_review_status=DownloadReviewProjectReviewStatus.COMPLETED,
        reference_review="O",
        artifact_results=artifact_results,
        passed_count=passed_count,
        failed_count=0,
        result_count=len(evaluations),
    )


def cleanup_download_dir(project, download_dir=None) -> CleanupOutcome:
    """프로젝트 다운로드 폴더를 삭제한다.

    삭제 대상은 AGENT_DOWNLOAD_BASE_DIR 아래에 있고 폴더명에 프로젝트번호가 포함된
    디렉터리로 제한한다.
    """
    raw_path = str(download_dir or project.download_dir or "").strip()
    if not raw_path:
        return CleanupOutcome(deleted=False, message="삭제할 다운로드 폴더가 없습니다.")

    target = Path(raw_path).resolve()
    base_dir = Path(getattr(settings, "AGENT_DOWNLOAD_BASE_DIR")).resolve()
    _validate_cleanup_target(project.project_number, base_dir, target)

    if not target.exists():
        project.zip_deleted_at = timezone.now()
        project.save(update_fields=["zip_deleted_at", "updated_at"])
        return CleanupOutcome(deleted=False, message="다운로드 폴더가 이미 없습니다.")

    file_count = sum(1 for item in target.rglob("*") if item.is_file())
    shutil.rmtree(target)

    project.zip_deleted_at = timezone.now()
    project.save(update_fields=["zip_deleted_at", "updated_at"])
    return CleanupOutcome(
        deleted=True,
        message="다운로드 폴더를 삭제했습니다.",
        file_count=file_count,
    )


def _evaluate_rule(rule, sequence, project, verify_result, file_summary):
    rule_type = (rule.rule_type or "").strip()
    if rule_type == "min_file_count":
        return _evaluate_min_file_count(rule, sequence, project, verify_result)
    if rule_type == "filename_contains_project_number":
        return _evaluate_filename_contains_project_number(rule, sequence, project, verify_result)
    if rule_type == "required_extension":
        return _evaluate_required_extension(rule, sequence, project, verify_result)
    if rule_type == "required_file_name_contains":
        return _evaluate_required_file_name_contains(rule, sequence, project, verify_result)
    if rule_type == "required_artifact_file":
        return _evaluate_required_artifact_file(rule, sequence, project, verify_result)
    if rule_type == "document_artifact_check":
        return _evaluate_document_artifact_check(rule, sequence, project, verify_result)
    if rule_type == "all_files_non_empty":
        return _evaluate_all_files_non_empty(rule, sequence, project, verify_result)

    raise DownloadReviewInspectionError(f"지원하지 않는 점검규칙 유형입니다: {rule_type or '(비어 있음)'}")


def _evaluate_min_file_count(rule, sequence, project, verify_result):
    config = rule.config_json or {}
    min_count = int(config.get("min_count") or 1)
    files = _matching_files(rule, verify_result)
    status = DownloadReviewRuleStatus.PASS if len(files) >= min_count else DownloadReviewRuleStatus.FAIL
    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected=f"{min_count}개 이상",
        actual=f"{len(files)}개",
        message="파일 개수 기준을 충족했습니다." if status == DownloadReviewRuleStatus.PASS else "파일 개수가 부족합니다.",
        file_path=_representative_path(files, project.project_number),
        file_name=_representative_name(files),
        raw_detail={"matched_file_count": len(files), "min_count": min_count},
    )


def _evaluate_filename_contains_project_number(rule, sequence, project, verify_result):
    files = _matching_files(rule, verify_result)
    matched = [file_info for file_info in files if project.project_number in file_info.name]
    status = DownloadReviewRuleStatus.PASS if matched else DownloadReviewRuleStatus.FAIL
    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected=f"파일명에 {project.project_number} 포함",
        actual=", ".join(file_info.name for file_info in matched[:5]) if matched else "일치 파일 없음",
        message="프로젝트번호가 포함된 파일을 확인했습니다." if matched else "프로젝트번호가 포함된 파일을 찾지 못했습니다.",
        file_path=_representative_path(matched or files, project.project_number),
        file_name=_representative_name(matched or files),
        raw_detail={"matched_file_count": len(matched), "total_file_count": len(files)},
    )


def _evaluate_required_extension(rule, sequence, project, verify_result):
    config = rule.config_json or {}
    extension = str(config.get("extension") or _extension_from_file_type(rule.target_file_type)).lower()
    if not extension.startswith("."):
        extension = f".{extension}"

    files = _matching_files(rule, verify_result, ignore_target_file_type=True)
    matched = [file_info for file_info in files if file_info.extension.lower() == extension]
    status = DownloadReviewRuleStatus.PASS if matched else DownloadReviewRuleStatus.FAIL
    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected=f"{extension} 파일 존재",
        actual=", ".join(file_info.name for file_info in matched[:5]) if matched else "일치 파일 없음",
        message=f"{extension} 파일을 확인했습니다." if matched else f"{extension} 파일을 찾지 못했습니다.",
        file_path=_representative_path(matched or files, project.project_number),
        file_name=_representative_name(matched or files),
        raw_detail={"extension": extension, "matched_file_count": len(matched)},
    )


def _evaluate_required_file_name_contains(rule, sequence, project, verify_result):
    config = rule.config_json or {}
    contains = str(config.get("contains") or "").strip()
    if not contains:
        raise DownloadReviewInspectionError(f"{rule.name} 규칙의 contains 설정이 없습니다.")

    files = _matching_files(rule, verify_result)
    matched = [file_info for file_info in files if contains in file_info.name]
    status = DownloadReviewRuleStatus.PASS if matched else DownloadReviewRuleStatus.FAIL
    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected=f"파일명에 {contains} 포함",
        actual=", ".join(file_info.name for file_info in matched[:5]) if matched else "일치 파일 없음",
        message=f"{contains} 파일을 확인했습니다." if matched else f"{contains} 파일을 찾지 못했습니다.",
        file_path=_representative_path(matched or files, project.project_number),
        file_name=_representative_name(matched or files),
        raw_detail={"contains": contains, "matched_file_count": len(matched)},
    )


def _evaluate_required_artifact_file(rule, sequence, project, verify_result):
    config = rule.config_json or {}
    name_keywords = _resolved_keywords(config.get("filename_keywords") or [], project)
    if not name_keywords:
        raise DownloadReviewInspectionError(f"{rule.name} 규칙의 filename_keywords 설정이 없습니다.")

    files, selected_folder = _files_in_configured_folder(rule, verify_result)
    extensions = _configured_extensions(config, rule.target_file_type)
    matched = [
        file_info
        for file_info in files
        if _name_contains_all(file_info.name, name_keywords)
        and _extension_matches(file_info.extension, extensions)
    ]

    exact_count = config.get("exact_count")
    min_count = int(config.get("min_count") or 1)
    if exact_count is not None:
        expected_count = int(exact_count)
        passed = len(matched) == expected_count
        expected = f"{expected_count}개"
    else:
        passed = len(matched) >= min_count
        expected = f"{min_count}개 이상"

    status = DownloadReviewRuleStatus.PASS if passed else DownloadReviewRuleStatus.FAIL
    message = _artifact_file_message(config, status, len(matched), exact_count)
    expected_parts = [
        "파일명에 " + ", ".join(name_keywords) + " 포함",
        expected,
    ]
    if extensions:
        expected_parts.append("확장자 " + ", ".join(extensions))

    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected=" / ".join(expected_parts),
        actual=_matched_files_actual(matched),
        message=message,
        file_path=_representative_path(matched or files, project.project_number),
        file_name=_representative_name(matched or files),
        raw_detail={
            "matched_file_count": len(matched),
            "folder_keyword_chain": config.get("folder_keyword_chain") or [],
            "selected_folder": selected_folder,
            "filename_keywords": name_keywords,
            "extensions": extensions,
            "matched_files": [
                _display_path(file_info.path, project.project_number)
                for file_info in matched[:20]
            ],
        },
    )


def _evaluate_document_artifact_check(rule, sequence, project, verify_result):
    config = rule.config_json or {}
    name_keywords = _resolved_keywords(config.get("filename_keywords") or [], project)
    if not name_keywords:
        raise DownloadReviewInspectionError(f"{rule.name} 규칙의 filename_keywords 설정이 없습니다.")

    files, selected_folder = _files_in_configured_folder(rule, verify_result)
    matched = [
        file_info
        for file_info in files
        if _name_contains_all(file_info.name, name_keywords)
    ]
    file_check = _evaluate_required_file_specs(config, matched)
    content_check = _evaluate_content_checks(config, matched, project) if file_check["passed"] else {
        "passed": True,
        "expected": [],
        "actual": [],
        "message": "",
        "details": [],
    }

    passed = file_check["passed"] and content_check["passed"]
    status = DownloadReviewRuleStatus.PASS if passed else DownloadReviewRuleStatus.FAIL
    message = (
        config.get("pass_message")
        if passed
        else file_check["message"] or content_check["message"] or config.get("missing_message")
    ) or ("문서 내용을 확인했습니다." if passed else "문서 내용이 기준과 일치하지 않습니다.")
    expected = " / ".join([*file_check["expected"], *content_check["expected"]])
    actual = " / ".join([*file_check["actual"], *content_check["actual"]]) or _matched_files_actual(matched)

    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected=expected,
        actual=actual,
        message=message,
        file_path=_representative_path(matched or files, project.project_number),
        file_name=_representative_name(matched or files),
        raw_detail={
            "matched_file_count": len(matched),
            "folder_keyword_chain": config.get("folder_keyword_chain") or [],
            "selected_folder": selected_folder,
            "filename_keywords": name_keywords,
            "file_checks": file_check["details"],
            "content_checks": content_check["details"],
            "matched_files": [
                _display_path(file_info.path, project.project_number)
                for file_info in matched[:20]
            ],
        },
    )


def _evaluate_all_files_non_empty(rule, sequence, project, verify_result):
    files = _matching_files(rule, verify_result)
    empty_files = [file_info for file_info in files if file_info.size == 0]
    status = (
        DownloadReviewRuleStatus.PASS
        if files and not empty_files
        else DownloadReviewRuleStatus.FAIL
    )
    return RuleEvaluation(
        rule=rule,
        sequence=sequence,
        status=status,
        expected="모든 파일 크기 1 byte 이상",
        actual="0 byte 파일 없음" if status == DownloadReviewRuleStatus.PASS else ", ".join(file_info.name for file_info in empty_files[:5]) or "검사 대상 파일 없음",
        message="빈 파일이 없습니다." if status == DownloadReviewRuleStatus.PASS else "빈 파일이 있거나 검사 대상 파일이 없습니다.",
        file_path=_representative_path(empty_files or files, project.project_number),
        file_name=_representative_name(empty_files or files),
        raw_detail={"empty_file_count": len(empty_files), "matched_file_count": len(files)},
    )


def _matching_files(rule, verify_result, *, ignore_target_file_type=False):
    files = _inspection_files(verify_result)
    pattern = (rule.target_file_pattern or "").strip()
    file_type = (rule.target_file_type or "any").strip().lower()

    if pattern:
        files = [file_info for file_info in files if fnmatch.fnmatch(file_info.name, pattern)]

    if not ignore_target_file_type and file_type and file_type != "any":
        extension = _extension_from_file_type(file_type)
        if extension:
            files = [file_info for file_info in files if file_info.extension.lower() == extension]

    return files


def _inspection_files(verify_result):
    files = list(verify_result.files or [])
    expanded_files = list(files)
    for file_info in files:
        if file_info.extension.lower() != ".zip":
            continue
        try:
            expanded_files.extend(_zip_entry_files(file_info))
        except (BadZipFile, OSError) as exc:
            raise DownloadReviewInspectionError(
                f"zip 파일을 읽을 수 없습니다: {file_info.name}"
            ) from exc
    return expanded_files


def _zip_entry_files(zip_file_info):
    entries = []
    with ZipFile(zip_file_info.path) as zip_file:
        for entry in zip_file.infolist():
            if entry.is_dir():
                continue
            inner_path = entry.filename.replace("\\", "/")
            inner_name = PurePosixPath(inner_path).name
            entries.append(
                FileInfo(
                    name=inner_name,
                    path=f"{zip_file_info.path}::{inner_path}",
                    size=entry.file_size,
                    extension=PurePosixPath(inner_name).suffix.lower(),
                )
            )
    return entries


def _read_file_bytes(file_info):
    raw_path = str(file_info.path or "")
    if "::" not in raw_path:
        return Path(raw_path).read_bytes()

    zip_path, inner_path = raw_path.split("::", 1)
    with ZipFile(zip_path) as zip_file:
        return zip_file.read(inner_path)


def _files_in_configured_folder(rule, verify_result):
    config = rule.config_json or {}
    files = _matching_files(rule, verify_result)
    folder_keyword_chain = [
        str(item).strip()
        for item in config.get("folder_keyword_chain") or []
        if str(item).strip()
    ]
    if not folder_keyword_chain:
        return files, ""

    selected_folder_segments = None
    for file_info in files:
        folder_segments = _folder_segments(file_info.path)
        matched_indices = _folder_keyword_chain_indices(folder_segments, folder_keyword_chain)
        if matched_indices:
            selected_folder_segments = folder_segments[: matched_indices[-1] + 1]
            break

    if not selected_folder_segments:
        return [], ""

    selected_files = [
        file_info
        for file_info in files
        if _folder_segments(file_info.path)[: len(selected_folder_segments)] == selected_folder_segments
    ]
    return selected_files, "/".join(selected_folder_segments)


def _folder_segments(path):
    normalized = str(path or "").replace("\\", "/")
    if "::" in normalized:
        normalized = normalized.split("::", 1)[1]
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return []
    return parts[:-1]


def _folder_keyword_chain_indices(folder_segments, keyword_chain):
    indices = []
    start = 0
    for keyword in keyword_chain:
        found = None
        for index in range(start, len(folder_segments)):
            if keyword in folder_segments[index]:
                found = index
                break
        if found is None:
            return []
        indices.append(found)
        start = found + 1
    return indices


def _resolved_keywords(keywords, project):
    resolved = []
    for keyword in keywords:
        value = _resolve_rule_value(str(keyword), project)
        if value:
            resolved.append(value)
    return resolved


def _resolve_rule_value(value, project):
    ecm_row = project.ecm_row_json or {}
    replacements = {
        "{project_number}": project.project_number,
        "{프로젝트번호}": project.project_number,
        "{product}": ecm_row.get("product") or ecm_row.get("제품명") or "",
        "{제품명}": ecm_row.get("product") or ecm_row.get("제품명") or "",
        "{pl}": ecm_row.get("pl") or ecm_row.get("시험PL") or "",
        "{PL}": ecm_row.get("pl") or ecm_row.get("시험PL") or "",
        "{wd}": ecm_row.get("wd") or ecm_row.get("WD") or "",
        "{WD}": ecm_row.get("wd") or ecm_row.get("WD") or "",
    }
    for placeholder, replacement in replacements.items():
        value = value.replace(placeholder, str(replacement))
    return value.strip()


def _configured_extensions(config, target_file_type):
    raw_extensions = config.get("extensions")
    if raw_extensions is None:
        extension = _extension_from_file_type(target_file_type)
        return [extension] if extension else []
    extensions = []
    for extension in raw_extensions:
        normalized = _normalize_extension(extension)
        if normalized:
            extensions.append(normalized)
    return extensions


def _normalize_extension(extension):
    value = str(extension or "").strip().lower()
    if not value or value == "any":
        return ""
    if value.startswith("."):
        return value
    return f".{value}"


def _name_contains_all(file_name, keywords):
    return all(keyword in file_name for keyword in keywords)


def _extension_matches(extension, extensions):
    if not extensions:
        return True
    return str(extension or "").lower() in extensions


def _artifact_file_message(config, status, matched_count, exact_count):
    if status == DownloadReviewRuleStatus.PASS:
        return config.get("pass_message") or "대상 파일을 확인했습니다."
    if exact_count is not None and matched_count > int(exact_count):
        return config.get("multiple_message") or "대상 파일이 여러개 존재합니다."
    return config.get("missing_message") or "파일이 없습니다."


def _matched_files_actual(files):
    if not files:
        return "일치 파일 없음"
    return ", ".join(file_info.name for file_info in files[:5])


def _evaluate_required_file_specs(config, matched_files):
    specs = config.get("required_files") or []
    if not specs:
        specs = [
            {
                "extensions": config.get("extensions") or [],
                "exact_count": config.get("exact_count"),
                "min_count": config.get("min_count") or 1,
            }
        ]

    passed = True
    expected = []
    actual = []
    details = []
    message = ""
    for spec in specs:
        extensions = _configured_extensions(spec, "any")
        files = [
            file_info
            for file_info in matched_files
            if _extension_matches(file_info.extension, extensions)
        ]
        exact_count = spec.get("exact_count")
        min_count = int(spec.get("min_count") or 1)
        if exact_count is not None:
            count_expected = int(exact_count)
            spec_passed = len(files) == count_expected
            count_text = f"{count_expected}개"
        else:
            spec_passed = len(files) >= min_count
            count_text = f"{min_count}개 이상"

        extension_text = ", ".join(extensions) if extensions else "확장자 무관"
        expected.append(f"{extension_text} {count_text}")
        actual.append(f"{extension_text} {len(files)}개")
        details.append({
            "extensions": extensions,
            "expected": count_text,
            "actual_count": len(files),
            "matched_files": [file_info.name for file_info in files[:10]],
            "passed": spec_passed,
        })
        if not spec_passed:
            passed = False
            message = spec.get("message") or config.get("missing_message") or "필요한 파일이 없습니다."

    return {
        "passed": passed,
        "expected": expected,
        "actual": actual,
        "message": message,
        "details": details,
    }


def _evaluate_content_checks(config, matched_files, project):
    passed = True
    expected = []
    actual = []
    details = []
    message = ""

    for check in config.get("content_checks") or []:
        extensions = _configured_extensions(check, "any")
        files = [
            file_info
            for file_info in matched_files
            if _extension_matches(file_info.extension, extensions)
        ]
        if not files:
            check_result = {
                "passed": False,
                "expected": _content_check_expected(check, project),
                "actual": "검사 대상 파일 없음",
                "message": check.get("missing_message") or "검사 대상 파일이 없습니다.",
                "detail": {"extensions": extensions},
            }
        else:
            check_result = _run_content_check(check, files[0], project)

        expected.append(check_result["expected"])
        actual.append(check_result["actual"])
        details.append({
            **check_result.get("detail", {}),
            "type": check.get("type"),
            "file_name": files[0].name if files else "",
            "passed": check_result["passed"],
        })
        if not check_result["passed"] and passed:
            passed = False
            message = check_result["message"]

    return {
        "passed": passed,
        "expected": expected,
        "actual": actual,
        "message": message,
        "details": details,
    }


def _run_content_check(check, file_info, project):
    check_type = str(check.get("type") or "").strip()
    if check_type == "docx_table_next_cell_equals":
        return _check_docx_table_next_cell_equals(check, file_info, project)
    if check_type == "pdf_first_page_label_value_contains":
        return _check_pdf_first_page_label_value_contains(check, file_info, project)
    if check_type == "docx_text_contains":
        return _check_docx_text_contains(check, file_info, project)
    if check_type == "docx_next_paragraph_matches":
        return _check_docx_next_paragraph_matches(check, file_info, project)
    raise DownloadReviewInspectionError(f"지원하지 않는 문서 내용 검사 유형입니다: {check_type or '(비어 있음)'}")


def _check_docx_table_next_cell_equals(check, file_info, project):
    label = str(check.get("label") or "").strip()
    expected_value = _resolve_rule_value(str(check.get("expected") or ""), project)
    rows = _docx_table_rows(file_info)
    actual_value = _find_next_cell_by_label(rows, label)
    passed = _normalize_compare(actual_value, check) == _normalize_compare(expected_value, check)
    return _content_result(
        check,
        passed,
        expected=f"{label} 오른쪽 셀 = {expected_value}",
        actual=f"{label} 오른쪽 셀 = {actual_value or '(없음)'}",
        detail={"label": label, "expected_value": expected_value, "actual_value": actual_value},
    )


def _check_pdf_first_page_label_value_contains(check, file_info, project):
    label = str(check.get("label") or "").strip()
    expected_value = _resolve_rule_value(str(check.get("expected") or ""), project)
    text = _pdf_page_text(file_info, page_index=int(check.get("page_index") or 0))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    window_size = int(check.get("line_window") or 3)
    actual_value = ""
    for index, line in enumerate(lines):
        if label not in line:
            continue
        window = lines[index:index + window_size + 1]
        actual_value = " ".join(window)
        if expected_value in actual_value:
            break
    passed = bool(actual_value and expected_value in actual_value)
    return _content_result(
        check,
        passed,
        expected=f"PDF 1페이지 {label} 주변에 {expected_value} 포함",
        actual=actual_value or f"PDF 1페이지에서 {label} 없음",
        detail={"label": label, "expected_value": expected_value, "text_excerpt": lines[:20]},
    )


def _check_docx_text_contains(check, file_info, project):
    expected_text = _resolve_rule_value(str(check.get("text") or ""), project)
    paragraphs = _docx_paragraphs(file_info)
    matched = _find_matching_paragraph(paragraphs, expected_text, check)
    passed = matched is not None
    return _content_result(
        check,
        passed,
        expected=f"문서에 '{expected_text}' 포함",
        actual=matched or "일치 문장 없음",
        detail={"expected_text": expected_text, "matched_text": matched or ""},
    )


def _check_docx_next_paragraph_matches(check, file_info, project):
    after_text = _resolve_rule_value(str(check.get("after_text") or ""), project)
    pattern = str(check.get("regex") or "").strip()
    paragraphs = _docx_paragraphs(file_info)
    matched_index = _find_matching_paragraph_index(paragraphs, after_text, check)
    next_text = ""
    if matched_index is not None:
        for paragraph in paragraphs[matched_index + 1:]:
            if paragraph.strip():
                next_text = paragraph.strip()
                break
    passed = bool(next_text and re.search(pattern, next_text))
    return _content_result(
        check,
        passed,
        expected=f"'{after_text}' 다음 문단이 {pattern} 형식",
        actual=next_text or "다음 문단 없음",
        detail={"after_text": after_text, "regex": pattern, "actual_text": next_text},
    )


def _content_result(check, passed, *, expected, actual, detail):
    return {
        "passed": passed,
        "expected": expected,
        "actual": actual,
        "message": (
            check.get("pass_message")
            if passed
            else check.get("failure_message")
        ) or ("문서 내용을 확인했습니다." if passed else "문서 내용이 기준과 일치하지 않습니다."),
        "detail": detail,
    }


def _content_check_expected(check, project):
    if "expected" in check:
        return _resolve_rule_value(str(check.get("expected") or ""), project)
    if "text" in check:
        return _resolve_rule_value(str(check.get("text") or ""), project)
    return str(check.get("type") or "")


def _docx_root(file_info):
    data = _read_file_bytes(file_info)
    with ZipFile(BytesIO(data)) as docx_file:
        return etree.fromstring(docx_file.read("word/document.xml"))


def _docx_paragraphs(file_info):
    root = _docx_root(file_info)
    ns = _word_ns()
    paragraphs = []
    for paragraph in root.xpath(".//w:p", namespaces=ns):
        text = "".join(paragraph.xpath(".//w:t/text()", namespaces=ns)).strip()
        if text:
            paragraphs.append(_normalize_spaces(text))
    return paragraphs


def _docx_table_rows(file_info):
    root = _docx_root(file_info)
    ns = _word_ns()
    rows = []
    for table in root.xpath(".//w:tbl", namespaces=ns):
        for row in table.xpath("./w:tr", namespaces=ns):
            cells = []
            for cell in row.xpath("./w:tc", namespaces=ns):
                cells.append(_word_cell_text(cell, ns))
            rows.append(cells)
    return rows


def _word_cell_text(cell, ns):
    paragraphs = []
    for paragraph in cell.xpath("./w:p", namespaces=ns):
        text = "".join(paragraph.xpath(".//w:t/text()", namespaces=ns)).strip()
        if text:
            paragraphs.append(text)
    if not paragraphs:
        paragraphs = ["".join(cell.xpath(".//w:t/text()", namespaces=ns)).strip()]
    return _normalize_spaces(" ".join(paragraphs))


def _word_ns():
    return {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _find_next_cell_by_label(rows, label):
    target = _normalize_label(label)
    for row in rows:
        for index, cell in enumerate(row[:-1]):
            if _normalize_label(cell) == target:
                return row[index + 1].strip()
    return ""


def _pdf_page_text(file_info, *, page_index=0):
    import fitz

    data = _read_file_bytes(file_info)
    with fitz.open(stream=data, filetype="pdf") as document:
        if document.page_count <= page_index:
            return ""
        return document[page_index].get_text("text")


def _find_matching_paragraph(paragraphs, expected_text, check):
    index = _find_matching_paragraph_index(paragraphs, expected_text, check)
    return paragraphs[index] if index is not None else None


def _find_matching_paragraph_index(paragraphs, expected_text, check):
    expected = _normalize_content(expected_text, check)
    for index, paragraph in enumerate(paragraphs):
        actual = _normalize_content(paragraph, check)
        if expected and expected in actual:
            return index
    return None


def _normalize_content(value, check):
    text = str(value or "")
    if check.get("remove_whitespace"):
        return re.sub(r"\s+", "", text)
    if check.get("normalize_whitespace", True):
        return _normalize_spaces(text)
    return text


def _normalize_compare(value, check):
    text = str(value or "")
    if check.get("remove_whitespace"):
        return re.sub(r"\s+", "", text)
    return _normalize_spaces(text) if check.get("normalize_whitespace") else text.strip()


def _normalize_label(value):
    return re.sub(r"[\s:：]+", "", str(value or "")).lower()


def _normalize_spaces(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def _artifact_results_from_evaluations(evaluations):
    results = {}
    for evaluation in evaluations:
        column = _artifact_column(evaluation.rule)
        if not column:
            continue
        value = "O" if evaluation.status == DownloadReviewRuleStatus.PASS else "X"
        previous = results.get(column)
        if previous == "X":
            continue
        results[column] = value
    return results


def _artifact_column(rule):
    config = rule.config_json or {}
    configured = str(config.get("artifact_column") or "").strip()
    candidates = (configured, rule.code, rule.name)
    for candidate in candidates:
        if candidate in ARTIFACT_REVIEW_COLUMNS:
            return candidate
    return ""


def _extension_from_file_type(file_type):
    value = str(file_type or "").strip().lower()
    if not value or value == "any":
        return ""
    if value.startswith("."):
        return value
    return f".{value}"


def _representative_name(files):
    if not files:
        return ""
    if len(files) == 1:
        return files[0].name
    return f"{files[0].name} 외 {len(files) - 1}개"


def _representative_path(files, project_number):
    if not files:
        return ""
    return _display_path(files[0].path, project_number) or files[0].name


def _display_path(path, project_number):
    normalized = str(path or "").replace("\\", "/")
    index = normalized.find(project_number)
    if index >= 0:
        return normalized[index:]
    return Path(normalized).name


def _validate_cleanup_target(project_number, base_dir, target):
    try:
        target.relative_to(base_dir)
    except ValueError as exc:
        raise DownloadReviewCleanupSafetyError(
            "다운로드 폴더가 허용된 기본 경로 밖에 있어 삭제하지 않았습니다."
        ) from exc

    if target == base_dir:
        raise DownloadReviewCleanupSafetyError("다운로드 기본 폴더 자체는 삭제할 수 없습니다.")
    if not target.is_dir() and target.exists():
        raise DownloadReviewCleanupSafetyError("삭제 대상이 폴더가 아닙니다.")
    if project_number not in target.name:
        raise DownloadReviewCleanupSafetyError(
            "삭제 대상 폴더명에 프로젝트번호가 없어 삭제하지 않았습니다."
        )
