from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


CACHE_FILE_NAME = "rules_bundle.json"


@dataclass(frozen=True)
class RuleCacheSummary:
    exists: bool
    path: Path
    rulebase_version: str = ""
    engine_min_version: str = ""
    checksum: str = ""
    rule_count: int = 0
    saved_at: str = ""


def default_cache_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "GSCertLocalReview"
    return Path.home() / ".gscert_local_review"


def cache_file_path(cache_dir: Path | None = None) -> Path:
    return (cache_dir or default_cache_dir()) / CACHE_FILE_NAME


def load_rule_cache(cache_dir: Path | None = None) -> RuleCacheSummary:
    path = cache_file_path(cache_dir)
    if not path.exists():
        return RuleCacheSummary(exists=False, path=path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RuleCacheSummary(exists=False, path=path)
    return _summary_from_payload(path, payload, exists=True)


def save_rule_cache(payload: dict[str, Any], cache_dir: Path | None = None) -> RuleCacheSummary:
    path = cache_file_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    saved_payload = dict(payload)
    saved_payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(
        json.dumps(saved_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return _summary_from_payload(path, saved_payload, exists=True)


def _summary_from_payload(path: Path, payload: dict[str, Any], exists: bool) -> RuleCacheSummary:
    return RuleCacheSummary(
        exists=exists,
        path=path,
        rulebase_version=str(payload.get("rulebase_version") or ""),
        engine_min_version=str(payload.get("engine_min_version") or ""),
        checksum=str(payload.get("checksum") or ""),
        rule_count=int(payload.get("rule_count") or len(payload.get("rules") or [])),
        saved_at=str(payload.get("saved_at") or ""),
    )
