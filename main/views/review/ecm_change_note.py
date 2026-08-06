import re
import unicodedata
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from django.conf import settings

from main.models import DownloadReviewLog, DownloadReviewLogLevel


CHANGE_NOTE_EVENT_CODE = "change_note_detected"
CHANGE_NOTE_MAX_BYTES = 256 * 1024
_CHANGE_NOTE_KEYWORD = "수정"
_CHANGE_NOTE_EXTENSION = ".txt"


def change_note_summary(project):
    note = _locate_change_note(project, include_content=False)
    return {
        "available": bool(note.get("available")),
        "file_name": note.get("file_name", ""),
        "file_path": note.get("file_path", ""),
        "modified_at": note.get("modified_at", ""),
        "source": note.get("source", ""),
    }


def change_note_payload(project):
    return _locate_change_note(project, include_content=True)


def record_change_note_if_present(job, project, verify_result):
    file_info = _find_change_note_file_info(getattr(verify_result, "files", []) or [])
    if not file_info:
        return None

    payload = _payload_from_path(
        Path(str(file_info.path)),
        project,
        include_content=True,
        file_name=file_info.name,
        modified_at=getattr(file_info, "modified_at", None),
    )
    if not payload.get("available"):
        return None

    return DownloadReviewLog.objects.create(
        job=job,
        job_project=project,
        event_code=CHANGE_NOTE_EVENT_CODE,
        level=DownloadReviewLogLevel.INFO,
        message=f"{project.project_number} 수정 내용 파일 확인: {payload['file_name']}",
        detail_json=payload,
        admin_only=False,
    )


def _locate_change_note(project, *, include_content):
    path = _find_change_note_path(project)
    if path:
        payload = _payload_from_path(path, project, include_content=include_content)
        if payload.get("available"):
            return payload

    log = (
        DownloadReviewLog.objects
        .filter(job_project=project, event_code=CHANGE_NOTE_EVENT_CODE)
        .order_by("-created_at", "-id")
        .first()
    )
    if log:
        detail = dict(log.detail_json or {})
        detail["available"] = True
        detail["source"] = "log"
        if not include_content:
            detail.pop("content", None)
        return detail

    return {"available": False}


def _find_change_note_path(project):
    for root in _candidate_roots(project):
        try:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if path.is_file() and _is_change_note_name(path.name):
                    return path
        except OSError:
            continue
    return None


def _candidate_roots(project):
    roots = []
    if getattr(project, "download_dir", ""):
        roots.append(Path(project.download_dir))

    archive_base = getattr(settings, "AGENT_ARCHIVE_BASE_DIR", "")
    if archive_base:
        roots.append(Path(archive_base) / project.project_number)

    try:
        archive_logs = (
            DownloadReviewLog.objects
            .filter(job_project=project, event_code="archive_completed")
            .order_by("-created_at", "-id")[:3]
        )
        for log in archive_logs:
            archive_dir = (log.detail_json or {}).get("archive_dir")
            if archive_dir:
                roots.append(Path(archive_dir))
    except Exception:
        pass

    unique = []
    seen = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _find_change_note_file_info(files):
    for file_info in files:
        if _is_change_note_name(getattr(file_info, "name", "")):
            return file_info
    return None


def _is_change_note_name(name):
    normalized = unicodedata.normalize("NFKC", str(name or "")).casefold()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.endswith(_CHANGE_NOTE_EXTENSION) and _CHANGE_NOTE_KEYWORD in normalized


def _payload_from_path(path, project, *, include_content, file_name="", modified_at=None):
    try:
        stat = path.stat()
    except OSError:
        return {"available": False}

    payload = {
        "available": True,
        "file_name": file_name or path.name,
        "file_path": _display_project_path(path, project.project_number),
        "modified_at": _iso(modified_at or datetime.fromtimestamp(stat.st_mtime, tz=datetime_timezone.utc)),
        "size": stat.st_size,
        "source": "file",
    }
    if include_content:
        content, encoding, truncated = _read_change_note_text(path)
        payload.update({
            "content": content,
            "encoding": encoding,
            "truncated": truncated,
        })
    return payload


def _read_change_note_text(path):
    data = path.read_bytes()
    truncated = len(data) > CHANGE_NOTE_MAX_BYTES
    content = data[:CHANGE_NOTE_MAX_BYTES]
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        encoding = "utf-8-replace"
        text = content.decode("utf-8", "replace")

    if truncated:
        text += "\n\n[표시 가능한 최대 용량을 넘어 이후 내용은 생략되었습니다.]"
    return text, encoding, truncated


def _display_project_path(path, project_number):
    text = str(path).replace("\\", "/")
    number = str(project_number or "").strip()
    if not number:
        return text
    index = text.find(number)
    if index >= 0:
        return text[index:]
    return text


def _iso(value):
    if not value:
        return ""
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=datetime_timezone.utc)
    return value.isoformat()
