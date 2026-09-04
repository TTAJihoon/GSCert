import hashlib
import json
from pathlib import Path

from django.conf import settings

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
        "app_version": _local_review_app_version(),
    }


def _local_review_app_version():
    """빌드된 로컬 앱(dist 폴더)에 찍혀 있는 버전 문자열. 없으면 빈 문자열.

    다운로드 zip과 같은 폴더(main/views/review/ecm_download_review_api.py 의
    _local_review_package_dir와 동일 경로)를 봐서, 배포된 exe가 실제로 어떤
    버전인지 그대로 알려준다 — 별도로 버전을 관리/입력할 필요가 없다.
    """
    configured = getattr(settings, "LOCAL_REVIEW_APP_PACKAGE_DIR", None)
    package_dir = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(r"C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard").resolve()
    )
    # PyInstaller(onedir)는 --add-data 로 넣은 파일을 exe 옆이 아니라 _internal/ 밑에
    # 둔다(클라이언트의 resource_path() 가 sys._MEIPASS 로 찾는 것과 같은 위치).
    for version_path in (package_dir / "_internal" / "APP_VERSION", package_dir / "APP_VERSION"):
        if version_path.is_file():
            try:
                return version_path.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
    return ""


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
