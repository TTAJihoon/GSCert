"""KOLAS 결과서(시험성적서) 서버 저장소.

한 번이라도 요청된 프로젝트의 시험성적서를 서버 디스크에 프로젝트번호별로 보관해 두고, 같은
프로젝트를 다시 요청하면 ECM 에 접속하지 않고 저장본을 그대로 전달한다.

레이아웃 (기본 C:\\Users\\Administrator\\kolas, settings.KOLAS_REPORT_CACHE_DIR):
    <저장소>/<프로젝트번호>/word/<파일>
    <저장소>/<프로젝트번호>/pdf/<파일>
    <저장소>/<프로젝트번호>/_meta.json   ← 이 파일이 있어야 '완료된 저장본'으로 인정

- 저장은 임시 폴더에 전부 쓴 뒤 폴더째 이름을 바꿔 확정한다(동시 요청·중간 실패에도 반쪽 저장본이 안 남음).
- 일부 파일만 받은 프로젝트(무결성 실패 등)나 성적서를 못 찾은 프로젝트는 저장하지 않아 다음 요청 때 다시 시도한다.
- 저장본이 손상(파일 누락·크기 불일치)되면 저장본을 버리고 ECM 에서 다시 받는다.
- 저장소를 지우면(프로젝트 폴더 삭제) 다음 요청에서 ECM 최신본을 다시 받는다.
"""

import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = r"C:\Users\Administrator\kolas"
META_NAME = "_meta.json"
# 저장소에는 각 센터 ECM 에서 찾은 최종본(word/pdf)만 둔다. 분당 ECM 익명본은 저장하지 않는다.
KIND_DIRS = {"word": "word", "pdf": "pdf"}
KINDS = tuple(KIND_DIRS)


def cache_root():
    return Path(getattr(settings, "KOLAS_REPORT_CACHE_DIR", None) or DEFAULT_CACHE_DIR)


def project_dir(root, project_number):
    return Path(root) / project_number


def load(root, project_number):
    """완료된 저장본이면 [(kind, 파일명, Path)] 를, 없거나 손상됐으면 None 을 반환."""
    folder = project_dir(root, project_number)
    meta_path = folder / META_NAME
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        entries = []
        for item in meta["files"]:
            kind, name, size = item["kind"], item["name"], int(item["size"])
            if kind not in KIND_DIRS or Path(name).name != name:
                return None
            path = folder / KIND_DIRS[kind] / name
            if not path.is_file() or path.stat().st_size != size:
                return None
            entries.append((kind, name, path))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return entries or None


def save(root, project_number, files, *, center="", folder_name=""):
    """files: [(kind, 파일명, bytes)] 를 저장본으로 확정한다. 실패해도 예외를 던지지 않고 False 를 반환."""
    root = Path(root)
    tmp = root / f".tmp-{project_number}-{uuid.uuid4().hex[:8]}"
    final = project_dir(root, project_number)
    try:
        for kind, name, data in files:
            target = tmp / KIND_DIRS[kind] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        meta = {
            "project_number": project_number,
            "center": center,
            "ecm_folder": folder_name,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "files": [{"kind": kind, "name": name, "size": len(data)} for kind, name, data in files],
        }
        (tmp / META_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if final.exists():
            # 손상됐거나 갱신 요청으로 남은 이전 저장본을 교체한다.
            shutil.rmtree(final, ignore_errors=True)
        os.replace(tmp, final)
        return True
    except OSError as exc:
        logger.warning("KOLAS report cache save failed for %s: %s", project_number, exc)
        return False
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
