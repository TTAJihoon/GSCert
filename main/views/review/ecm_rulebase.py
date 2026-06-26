import hashlib
import json
import logging
import urllib.error
import urllib.request

from django.db import transaction

from main.models import DownloadReviewRule

logger = logging.getLogger("main.views.review.ecm_rulebase")


RULE_ENGINE_MIN_VERSION = "0.1.0"


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


def sync_rules_from_remote(remote_url: str) -> int:
    """원격 서버의 규칙 번들을 가져와 로컬 DB에 반영한다.

    기존 규칙을 비활성화하고 원격 규칙으로 교체한다.

    Returns:
        동기화된 규칙 수.
    Raises:
        RuntimeError: 네트워크 오류 또는 원격 응답이 실패인 경우.
    """
    logger.info("원격 규칙 번들 요청: %s", remote_url)
    req = urllib.request.Request(remote_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"원격 규칙 서버 접속 실패 ({remote_url}): {exc}") from exc

    if not data.get("success"):
        raise RuntimeError(
            f"원격 규칙 서버 응답 오류: {data.get('message', 'unknown error')}"
        )

    remote_rules = data.get("rules") or []
    if not remote_rules:
        logger.warning("원격 서버에 활성화된 규칙이 없습니다: %s", remote_url)
        return 0

    with transaction.atomic(using="workflow"):
        DownloadReviewRule.objects.all().update(enabled=False)
        for i, rule_data in enumerate(remote_rules):
            DownloadReviewRule.objects.update_or_create(
                code=rule_data["code"],
                defaults={
                    "name": rule_data.get("name", ""),
                    "target_file_pattern": rule_data.get("target_file_pattern", ""),
                    "target_file_type": rule_data.get("target_file_type", "any"),
                    "rule_type": rule_data.get("rule_type", ""),
                    "config_json": rule_data.get("config_json") or {},
                    "severity": rule_data.get("severity", "error"),
                    "version": rule_data.get("version", "1"),
                    "sort_order": rule_data.get("sort_order", i),
                    "enabled": True,
                },
            )

    logger.info("원격 규칙 %d개 동기화 완료.", len(remote_rules))
    return len(remote_rules)
