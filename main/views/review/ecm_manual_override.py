import logging
from dataclasses import replace
from types import SimpleNamespace

from django.utils import timezone

from main.models import DownloadReviewLog, DownloadReviewManualOverride, DownloadReviewRuleStatus


MANUAL_OVERRIDE_KEY = "manual_override"
logger = logging.getLogger(__name__)


def manual_overrides_for_project(project, rule_codes):
    codes = sorted({str(code or "").strip() for code in rule_codes if str(code or "").strip()})
    if not codes:
        return {}
    result = {}
    try:
        overrides = DownloadReviewManualOverride.objects.filter(
            center_code=str(project.center_code or "").strip(),
            project_number=str(project.project_number or "").strip(),
            rule_code__in=codes,
        )
        result = {override.rule_code: override for override in overrides}
    except Exception as exc:
        logger.warning("Manual override table lookup failed; using log fallback: %s", exc, exc_info=True)

    missing_codes = [code for code in codes if code not in result]
    if missing_codes:
        result.update(_manual_overrides_from_logs(project, missing_codes))
    return result


def _manual_overrides_from_logs(project, rule_codes):
    project_number = str(project.project_number or "").strip()
    center_code = str(project.center_code or "").strip()
    codes = set(rule_codes)
    overrides = {}
    try:
        logs = (
            DownloadReviewLog.objects
            .filter(event_code="manual_pass_override")
            .order_by("-created_at")[:1000]
        )
    except Exception as exc:
        logger.warning("Manual override log fallback lookup failed: %s", exc, exc_info=True)
        return overrides

    for log in logs:
        detail = log.detail_json if isinstance(log.detail_json, dict) else {}
        code = str(detail.get("rule_code") or "").strip()
        if code not in codes or code in overrides:
            continue
        if str(detail.get("project_number") or "").strip() != project_number:
            continue
        detail_center = str(detail.get("center_code") or "").strip()
        if detail_center and detail_center != center_code:
            continue
        overrides[code] = SimpleNamespace(
            id=f"log:{log.id}",
            memo=str(detail.get("memo") or ""),
            rule_code=code,
            rule_name=str(detail.get("rule_name") or ""),
            updated_at=log.created_at,
        )
        if len(overrides) == len(codes):
            break
    return overrides


def apply_manual_override_to_evaluation(evaluation, override):
    raw_detail = _detail_with_manual_override(
        evaluation.raw_detail or {},
        override,
        original_status=evaluation.status,
        original_message=evaluation.message,
    )
    return replace(
        evaluation,
        status=DownloadReviewRuleStatus.PASS,
        message=evaluation.message or "수동 적합 처리됨",
        raw_detail=raw_detail,
    )


def apply_manual_override_to_result(result, override, *, save=False):
    result.raw_detail_json = _detail_with_manual_override(
        result.raw_detail_json or {},
        override,
        original_status=result.status,
        original_message=result.message,
    )
    result.status = DownloadReviewRuleStatus.PASS
    if not result.message:
        result.message = "수동 적합 처리됨"
    if save:
        result.save(update_fields=["status", "message", "raw_detail_json"])
    return result


def mark_overrides_applied(overrides):
    ids = [override.id for override in overrides if getattr(override, "id", None)]
    if ids:
        DownloadReviewManualOverride.objects.filter(id__in=ids).update(last_applied_at=timezone.now())


def manual_override_public(raw_detail):
    if not isinstance(raw_detail, dict):
        return None
    value = raw_detail.get(MANUAL_OVERRIDE_KEY)
    if not isinstance(value, dict) or not value.get("applied"):
        return None
    return {
        "applied": True,
        "id": str(value.get("id") or ""),
        "memo": str(value.get("memo") or ""),
        "rule_code": str(value.get("rule_code") or ""),
        "rule_name": str(value.get("rule_name") or ""),
        "updated_at": str(value.get("updated_at") or ""),
        "original_status": str(value.get("original_status") or ""),
        "original_message": str(value.get("original_message") or ""),
    }


def _detail_with_manual_override(raw_detail, override, *, original_status, original_message):
    detail = dict(raw_detail) if isinstance(raw_detail, dict) else {}
    existing = detail.get(MANUAL_OVERRIDE_KEY)
    if isinstance(existing, dict) and existing.get("applied"):
        original_status = existing.get("original_status") or original_status
        original_message = existing.get("original_message") or original_message
    detail[MANUAL_OVERRIDE_KEY] = {
        "applied": True,
        "id": str(override.id),
        "memo": override.memo,
        "rule_code": override.rule_code,
        "rule_name": override.rule_name,
        "updated_at": override.updated_at.isoformat() if override.updated_at else "",
        "original_status": str(original_status or ""),
        "original_message": str(original_message or ""),
    }
    sub_checks = _manual_pass_sub_checks(detail.get("sub_checks"))
    if isinstance(sub_checks, list):
        detail["sub_checks"] = sub_checks
    return detail


def _manual_pass_sub_checks(sub_checks):
    if not isinstance(sub_checks, list):
        return sub_checks
    updated = []
    for item in sub_checks:
        if not isinstance(item, dict):
            updated.append(item)
            continue
        row = dict(item)
        row["passed"] = True
        row["manual_override"] = True
        updated.append(row)
    return updated
