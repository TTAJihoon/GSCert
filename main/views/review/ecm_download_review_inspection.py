import fnmatch
import shutil
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from main.models import (
    DownloadReviewProjectReviewStatus,
    DownloadReviewRule,
    DownloadReviewRuleResult,
    DownloadReviewRuleStatus,
)
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
    files = list(verify_result.files or [])
    pattern = (rule.target_file_pattern or "").strip()
    file_type = (rule.target_file_type or "any").strip().lower()

    if pattern:
        files = [file_info for file_info in files if fnmatch.fnmatch(file_info.name, pattern)]

    if not ignore_target_file_type and file_type and file_type != "any":
        extension = _extension_from_file_type(file_type)
        if extension:
            files = [file_info for file_info in files if file_info.extension.lower() == extension]

    return files


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
