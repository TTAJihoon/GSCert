"""프로젝트번호별 GS 기준정보 로컬 캐시.

규칙 번들(rule_cache.py)과 달리 이 정보는 프로젝트마다 값이 다르므로 규칙처럼
"현재 하나"를 캐시할 수 없다. 대신 온라인에서 성공적으로 조회한(직접 입력이 아닌)
결과를 프로젝트번호를 키로 모아두고, 같은 프로젝트를 오프라인에서 다시 열었을 때
그 값을 재사용해 매번 수동 재입력하지 않아도 되게 한다.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields as dataclass_fields
from datetime import datetime
from pathlib import Path

from .api_client import ProjectMetadata
from .rule_cache import default_cache_dir


CACHE_FILE_NAME = "project_metadata_cache.json"
_METADATA_FIELD_NAMES = {f.name for f in dataclass_fields(ProjectMetadata)}


def cache_file_path(cache_dir: Path | None = None) -> Path:
    return (cache_dir or default_cache_dir()) / CACHE_FILE_NAME


def _load_all(cache_dir: Path | None = None) -> dict[str, dict]:
    path = cache_file_path(cache_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_cached_metadata(
    project_number: str, cache_dir: Path | None = None
) -> tuple[ProjectMetadata, str] | None:
    """프로젝트번호로 캐시된 기준정보를 찾는다. 있으면 (metadata, 저장 시각 ISO 문자열)."""
    project_number = (project_number or "").strip()
    if not project_number:
        return None
    record = _load_all(cache_dir).get(project_number)
    if not isinstance(record, dict):
        return None
    fields_only = {name: str(record.get(name, "") or "") for name in _METADATA_FIELD_NAMES}
    cached_at = str(record.get("cached_at", "") or "")
    return ProjectMetadata(**fields_only), cached_at


def save_metadata(metadata: ProjectMetadata, cache_dir: Path | None = None) -> None:
    """온라인에서 성공적으로 조회한 기준정보만 저장한다(직접 입력은 캐시하지 않음 —
    미인증 프로젝트의 임시/추정값이 나중에 조용히 재사용되는 걸 막기 위해)."""
    project_number = (metadata.project_number or "").strip()
    if not project_number:
        return
    path = cache_file_path(cache_dir)
    all_records = _load_all(cache_dir)
    record = asdict(metadata)
    record["cached_at"] = datetime.now().isoformat(timespec="seconds")
    all_records[project_number] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(all_records, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def format_cache_age(cached_at: str) -> str:
    """'3일 전 조회', 저장 시각을 못 읽으면 '조회 시점 미상'."""
    if not cached_at:
        return "조회 시점 미상"
    try:
        saved = datetime.fromisoformat(cached_at)
    except ValueError:
        return "조회 시점 미상"
    days = max((datetime.now() - saved).days, 0)
    if days <= 0:
        return "오늘 조회"
    return f"{days}일 전 조회"
