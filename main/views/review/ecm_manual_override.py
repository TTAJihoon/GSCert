import logging
import re
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

from django.utils import timezone

from main.models import DownloadReviewLog, DownloadReviewManualOverride, DownloadReviewRuleStatus


MANUAL_OVERRIDE_KEY = "manual_override"
MANUAL_OVERRIDES_KEY = "manual_overrides"
SUB_CHECK_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
DEFAULT_MANUAL_PASS_MESSAGE = "수동 적합 처리됨"

logger = logging.getLogger(__name__)


@dataclass
class ManualOverrideGroup:
    rule_override: object | None = None
    sub_check_overrides: dict[str, object] = field(default_factory=dict)

    def __bool__(self):
        return bool(self.rule_override or self.sub_check_overrides)

    @property
    def primary(self):
        if self.rule_override is not None:
            return self.rule_override
        return next(iter(self.sub_check_overrides.values()), None)

    @property
    def id(self):
        return getattr(self.primary, "id", "")

    @property
    def memo(self):
        return getattr(self.primary, "memo", "")

    @property
    def rule_code(self):
        return getattr(self.primary, "rule_code", "")

    @property
    def rule_name(self):
        return getattr(self.primary, "rule_name", "")

    @property
    def updated_at(self):
        return getattr(self.primary, "updated_at", None)

    def all_overrides(self):
        items = []
        if self.rule_override is not None:
            items.append(self.rule_override)
        items.extend(self.sub_check_overrides.values())
        return items


def manual_overrides_for_project(project, rule_codes):
    codes = sorted({str(code or "").strip() for code in rule_codes if str(code or "").strip()})
    if not codes:
        return {}

    result: dict[str, ManualOverrideGroup] = {}
    try:
        overrides = DownloadReviewManualOverride.objects.filter(
            center_code=str(project.center_code or "").strip(),
            project_number=str(project.project_number or "").strip(),
            rule_code__in=codes,
        )
        for override in overrides:
            _add_override_to_groups(result, override)
    except Exception as exc:
        logger.warning("Manual override table lookup failed; using log fallback: %s", exc, exc_info=True)

    missing_codes = [code for code in codes if code not in result]
    if missing_codes:
        for code, group in _manual_overrides_from_logs(project, missing_codes).items():
            existing = result.setdefault(code, ManualOverrideGroup())
            if group.rule_override is not None:
                existing.rule_override = group.rule_override
            existing.sub_check_overrides.update(group.sub_check_overrides)
    return result


def _manual_overrides_from_logs(project, rule_codes):
    project_number = str(project.project_number or "").strip()
    center_code = str(project.center_code or "").strip()
    codes = set(rule_codes)
    overrides: dict[str, ManualOverrideGroup] = {}
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
        if code not in codes:
            continue
        group = overrides.get(code)
        if group and not _log_override_is_new_for_group(group, detail):
            continue
        if str(detail.get("project_number") or "").strip() != project_number:
            continue
        detail_center = str(detail.get("center_code") or "").strip()
        if detail_center and detail_center != center_code:
            continue
        override = SimpleNamespace(
            id=f"log:{log.id}",
            memo=str(detail.get("memo") or ""),
            rule_code=code,
            rule_name=str(detail.get("rule_name") or ""),
            sub_check_key=normalize_sub_check_key(detail.get("sub_check_key")),
            updated_at=log.created_at,
        )
        _add_override_to_groups(overrides, override)
    return overrides


def apply_manual_override_to_evaluation(evaluation, override):
    group = _coerce_override_group(override)
    if not group:
        return evaluation

    if group.rule_override is not None:
        if _is_pass_status(evaluation.status):
            return evaluation
        raw_detail = _detail_with_manual_override(
            evaluation.raw_detail or {},
            group.rule_override,
            original_status=evaluation.status,
            original_message=evaluation.message,
        )
        return replace(
            evaluation,
            status=DownloadReviewRuleStatus.PASS,
            message=evaluation.message or DEFAULT_MANUAL_PASS_MESSAGE,
            raw_detail=raw_detail,
        )

    raw_detail, applied = _detail_with_sub_check_overrides(
        evaluation.raw_detail or {},
        group.sub_check_overrides,
        original_status=evaluation.status,
        original_message=evaluation.message,
        only_when_failed=True,
    )
    if not applied:
        return evaluation
    return replace(
        evaluation,
        status=_status_from_detail(raw_detail, evaluation.status),
        message=_message_from_detail(raw_detail, evaluation.message),
        raw_detail=raw_detail,
    )


def apply_manual_override_to_result(result, override, *, save=False, sub_check_key="", only_when_failed=False):
    group = _coerce_override_group(override)
    if not group:
        return result

    if only_when_failed and _is_pass_status(result.status):
        return result

    target_key = normalize_sub_check_key(sub_check_key)
    if target_key:
        selected = group.sub_check_overrides.get(target_key) or group.primary
        result.raw_detail_json, _applied = _detail_with_sub_check_overrides(
            result.raw_detail_json or {},
            {target_key: selected},
            original_status=result.status,
            original_message=result.message,
            only_when_failed=only_when_failed,
        )
        result.status = _status_from_detail(result.raw_detail_json, result.status)
        result.message = _message_from_detail(result.raw_detail_json, result.message)
    else:
        selected = group.rule_override or group.primary
        result.raw_detail_json = _detail_with_manual_override(
            result.raw_detail_json or {},
            selected,
            original_status=result.status,
            original_message=result.message,
        )
        result.status = DownloadReviewRuleStatus.PASS
        if not result.message:
            result.message = DEFAULT_MANUAL_PASS_MESSAGE

    if save:
        result.save(update_fields=["status", "message", "raw_detail_json"])
    return result


def mark_overrides_applied(overrides):
    ids = []
    for override in overrides:
        for item in _iter_overrides(override):
            if isinstance(item, DownloadReviewManualOverride) and getattr(item, "id", None):
                ids.append(item.id)
    if ids:
        DownloadReviewManualOverride.objects.filter(id__in=ids).update(last_applied_at=timezone.now())


def applied_overrides_in_detail(raw_detail, override):
    group = _coerce_override_group(override)
    if not group:
        return []
    payload_ids = _manual_override_payload_ids(raw_detail)
    if not payload_ids:
        return []
    return [
        item for item in group.all_overrides()
        if str(getattr(item, "id", "") or "") in payload_ids
    ]


def manual_override_public(raw_detail):
    if not isinstance(raw_detail, dict):
        return None
    value = raw_detail.get(MANUAL_OVERRIDE_KEY)
    if not isinstance(value, dict) or not value.get("applied"):
        return None
    if _is_pass_status(value.get("original_status")):
        return None
    return {
        "applied": True,
        "id": str(value.get("id") or ""),
        "memo": str(value.get("memo") or ""),
        "rule_code": str(value.get("rule_code") or ""),
        "rule_name": str(value.get("rule_name") or ""),
        "sub_check_key": str(value.get("sub_check_key") or ""),
        "updated_at": str(value.get("updated_at") or ""),
        "original_status": str(value.get("original_status") or ""),
        "original_message": str(value.get("original_message") or ""),
    }


def sub_check_key_for_index(sub_check, index):
    if isinstance(sub_check, dict):
        for name in ("sub_check_key", "key", "id"):
            value = normalize_sub_check_key(sub_check.get(name))
            if value:
                return value
    return f"sub-{index}"


def normalize_sub_check_key(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return f"sub-{int(text)}"
    if SUB_CHECK_KEY_RE.fullmatch(text):
        return text[:80]
    return ""


def _detail_with_manual_override(raw_detail, override, *, original_status, original_message):
    detail = dict(raw_detail) if isinstance(raw_detail, dict) else {}
    existing = detail.get(MANUAL_OVERRIDE_KEY)
    if isinstance(existing, dict) and existing.get("applied"):
        original_status = existing.get("original_status") or original_status
        original_message = existing.get("original_message") or original_message
    payload = _override_payload(
        override,
        original_status=original_status,
        original_message=original_message,
        sub_check_key="",
    )
    detail[MANUAL_OVERRIDE_KEY] = payload
    sub_checks = _manual_pass_sub_checks(detail.get("sub_checks"), payload)
    if isinstance(sub_checks, list):
        detail["sub_checks"] = sub_checks
    return detail


def _detail_with_sub_check_overrides(raw_detail, overrides_by_key, *, original_status, original_message, only_when_failed=False):
    detail = dict(raw_detail) if isinstance(raw_detail, dict) else {}
    sub_checks = detail.get("sub_checks")
    if not isinstance(sub_checks, list):
        return detail, False

    normalized_overrides = {
        normalize_sub_check_key(key): override
        for key, override in (overrides_by_key or {}).items()
        if normalize_sub_check_key(key) and override is not None
    }
    if not normalized_overrides:
        return detail, False

    applied = False
    updated = []
    manual_overrides = detail.get(MANUAL_OVERRIDES_KEY)
    if not isinstance(manual_overrides, dict):
        manual_overrides = {}

    for index, item in enumerate(sub_checks, start=1):
        if not isinstance(item, dict):
            updated.append(item)
            continue
        row = dict(item)
        key = sub_check_key_for_index(row, index)
        row["sub_check_key"] = key
        override = normalized_overrides.get(key)
        if override is not None:
            if only_when_failed and not _sub_check_needs_manual_override(row, original_status):
                updated.append(row)
                continue
            existing = row.get(MANUAL_OVERRIDE_KEY)
            row_original_status = _original_status_for_sub_check(row, existing, original_status)
            row_original_message = _original_message_for_sub_check(row, existing, original_message)
            payload = _override_payload(
                override,
                original_status=row_original_status,
                original_message=row_original_message,
                sub_check_key=key,
            )
            row["passed"] = True
            row[MANUAL_OVERRIDE_KEY] = payload
            manual_overrides[key] = payload
            applied = True
        updated.append(row)

    if applied:
        detail["sub_checks"] = updated
        detail[MANUAL_OVERRIDES_KEY] = manual_overrides
    return detail, applied


def _manual_pass_sub_checks(sub_checks, override_payload=None):
    if not isinstance(sub_checks, list):
        return sub_checks
    updated = []
    for index, item in enumerate(sub_checks, start=1):
        if not isinstance(item, dict):
            updated.append(item)
            continue
        row = dict(item)
        row["sub_check_key"] = sub_check_key_for_index(row, index)
        row["passed"] = True
        row[MANUAL_OVERRIDE_KEY] = override_payload if override_payload is not None else True
        updated.append(row)
    return updated


def _add_override_to_groups(groups, override):
    code = str(getattr(override, "rule_code", "") or "").strip()
    if not code:
        return
    group = groups.setdefault(code, ManualOverrideGroup())
    key = normalize_sub_check_key(getattr(override, "sub_check_key", ""))
    if key:
        group.sub_check_overrides.setdefault(key, override)
    else:
        group.rule_override = override


def _log_override_is_new_for_group(group, detail):
    key = normalize_sub_check_key(detail.get("sub_check_key"))
    if key:
        return key not in group.sub_check_overrides
    return group.rule_override is None


def _coerce_override_group(override):
    if isinstance(override, ManualOverrideGroup):
        return override
    if override is None:
        return ManualOverrideGroup()
    group = ManualOverrideGroup()
    key = normalize_sub_check_key(getattr(override, "sub_check_key", ""))
    if key:
        group.sub_check_overrides[key] = override
    else:
        group.rule_override = override
    return group


def _iter_overrides(value):
    if isinstance(value, ManualOverrideGroup):
        return value.all_overrides()
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value] if value is not None else []


def _override_payload(override, *, original_status, original_message, sub_check_key):
    updated_at = getattr(override, "updated_at", None)
    return {
        "applied": True,
        "id": str(getattr(override, "id", "")),
        "memo": getattr(override, "memo", ""),
        "rule_code": getattr(override, "rule_code", ""),
        "rule_name": getattr(override, "rule_name", ""),
        "sub_check_key": normalize_sub_check_key(sub_check_key),
        "updated_at": updated_at.isoformat() if updated_at else "",
        "original_status": str(original_status or ""),
        "original_message": str(original_message or ""),
    }


def _original_status_for_sub_check(row, existing, fallback):
    if isinstance(existing, dict) and existing.get("applied"):
        return existing.get("original_status") or fallback
    if row.get("passed") is True:
        return DownloadReviewRuleStatus.PASS
    if row.get("passed") is False:
        return DownloadReviewRuleStatus.FAIL
    return fallback


def _original_message_for_sub_check(row, existing, fallback):
    if isinstance(existing, dict) and existing.get("applied"):
        return existing.get("original_message") or fallback
    return row.get("message") or fallback


def _status_from_detail(raw_detail, fallback):
    sub_checks = raw_detail.get("sub_checks") if isinstance(raw_detail, dict) else None
    if not isinstance(sub_checks, list) or not sub_checks:
        return fallback
    values = [item.get("passed") for item in sub_checks if isinstance(item, dict)]
    if values and all(value is True for value in values):
        return DownloadReviewRuleStatus.PASS
    if any(value is False for value in values):
        return DownloadReviewRuleStatus.FAIL
    return fallback


def _manual_override_payload_ids(raw_detail):
    if not isinstance(raw_detail, dict):
        return set()

    payloads = []
    root_payload = raw_detail.get(MANUAL_OVERRIDE_KEY)
    if isinstance(root_payload, dict):
        payloads.append(root_payload)

    manual_overrides = raw_detail.get(MANUAL_OVERRIDES_KEY)
    if isinstance(manual_overrides, dict):
        payloads.extend(item for item in manual_overrides.values() if isinstance(item, dict))

    sub_checks = raw_detail.get("sub_checks")
    if isinstance(sub_checks, list):
        for item in sub_checks:
            if not isinstance(item, dict):
                continue
            payload = item.get(MANUAL_OVERRIDE_KEY)
            if isinstance(payload, dict):
                payloads.append(payload)

    return {
        str(payload.get("id") or "")
        for payload in payloads
        if payload.get("applied") and str(payload.get("id") or "")
    }


def _sub_check_needs_manual_override(row, fallback_status):
    if row.get("passed") is False:
        return True
    if row.get("passed") is True:
        return False
    return not _is_pass_status(fallback_status)


def _is_pass_status(value):
    return str(value or "").strip().lower() == str(DownloadReviewRuleStatus.PASS)


def _message_from_detail(raw_detail, fallback):
    if _status_from_detail(raw_detail, fallback) == DownloadReviewRuleStatus.PASS:
        return fallback or DEFAULT_MANUAL_PASS_MESSAGE
    sub_checks = raw_detail.get("sub_checks") if isinstance(raw_detail, dict) else None
    if isinstance(sub_checks, list):
        for item in sub_checks:
            if isinstance(item, dict) and item.get("passed") is False:
                return item.get("message") or fallback
    return fallback
