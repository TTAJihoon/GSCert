import hashlib
import json

from main.models import DownloadReviewRule


# 현재 규칙셋을 실행하려면 최소 이 엔진 버전이 필요하다. 엔진에 새 규칙유형/검사옵션이
# 추가되어 구버전 엔진에서 오작동할 수 있으면 이 값을 올린다.
# 0.2.0: docx_footer/header_not_contains 검사유형, rawdata folder_check 옵션
#        (min_images/min_child_folders/pass_if_file_name_contains), 센터별 담당자 등.
RULE_ENGINE_MIN_VERSION = "0.2.0"


def get_rulebase_manifest_payload():
    rules = _serialized_enabled_rules()
    checksum = _rules_checksum(rules)
    return {
        "success": True,
        "rulebase_version": _rulebase_version(rules, checksum),
        "engine_min_version": RULE_ENGINE_MIN_VERSION,
        "checksum": f"sha256:{checksum}",
        "rule_count": len(rules),
        "published_at": _latest_updated_at(rules),
    }


def get_rulebase_bundle_payload(version=None):
    rules = _serialized_enabled_rules()
    checksum = _rules_checksum(rules)
    rulebase_version = _rulebase_version(rules, checksum)
    if version and version != rulebase_version:
        return {
            "success": False,
            "error_code": "rulebase_version_not_found",
            "message": "Requested rulebase version is not available.",
            "current_version": rulebase_version,
        }, 404

    return {
        "success": True,
        "rulebase_version": rulebase_version,
        "engine_min_version": RULE_ENGINE_MIN_VERSION,
        "checksum": f"sha256:{checksum}",
        "rule_count": len(rules),
        "published_at": _latest_updated_at(rules),
        "rules": rules,
    }, 200


def _serialized_enabled_rules():
    rules = (
        DownloadReviewRule.objects
        .filter(enabled=True)
        .order_by("sort_order", "name", "id")
    )
    return [_serialize_rule(rule) for rule in rules]


def _serialize_rule(rule):
    return {
        "code": rule.code,
        "name": rule.name,
        "target_file_pattern": rule.target_file_pattern,
        "target_file_type": rule.target_file_type,
        "rule_type": rule.rule_type,
        "config_json": rule.config_json or {},
        "severity": rule.severity,
        "version": rule.version,
        "sort_order": rule.sort_order,
        "enabled": rule.enabled,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else "",
    }


def _rules_checksum(rules):
    raw = json.dumps(rules, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _rulebase_version(rules, checksum):
    latest = _latest_updated_at(rules)
    if not rules:
        return "empty"
    if latest:
        compact = latest.replace("-", "").replace(":", "").replace(".", "")
        compact = compact.replace("+", "").replace("T", "")
        return f"{compact[:14]}-{checksum[:12]}"
    return checksum[:12]


def _latest_updated_at(rules):
    values = [rule.get("updated_at") for rule in rules if rule.get("updated_at")]
    if not values:
        return ""
    return max(values)
