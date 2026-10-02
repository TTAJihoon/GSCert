"""점검 때 보관한 산출물(`AGENT_ARCHIVE_BASE_DIR`/<프로젝트번호>)을 ECM 클라이언트처럼 보여주는 어댑터.

산출물 폴더 팝업은 보관본이 있으면 ECM 에서 다시 받지 않고 이 폴더에서 읽는다. 공유 폴더는 중간 부분만 읽을 수 있어
큰 zip 도 목록은 0.1초, 파일 하나는 즉시 꺼낼 수 있다(ECM 은 전체를 받아야 한다).

- 점검 때마다 보관 폴더를 통째로 교체하므로(워커 `_archive_download_dir_safely`) 내용은 마지막 점검 시점의 산출물이다.
  교체가 끝난 시각은 폴더 안 `.gscert_archive.json` 에 적힌다(화면 표시용, 목록에는 나오지 않는다).
- ECM 클라이언트와 같은 메서드(folder_contents / walk_files / blob_stream)를 가져 폴더 탐색 코드를 그대로 쓴다.
- 경로 안전: 항목은 서버가 서명한 토큰으로만 열리지만, 어댑터도 보관 폴더 밖(`..`, 절대 경로, 링크)은 열지 않는다.
"""

import json
import logging
import os
import unicodedata
from datetime import datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

ARCHIVE_CENTER = "archive"          # 폴더 탐색 토큰의 센터 값(실제 ECM 센터가 아니라 보관본)
MARKER_NAME = ".gscert_archive.json"
HIDDEN_PREFIXES = (".gscert", ".tmp-")


class ArchiveError(Exception):
    pass


def archive_base():
    base = str(getattr(settings, "AGENT_ARCHIVE_BASE_DIR", "") or "").strip()
    return Path(base) if base else None


def project_dir(project_number):
    base = archive_base()
    if base is None:
        return None
    name = unicodedata.normalize("NFC", str(project_number or ""))
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    return base / name


def find_project_archive(project_number):
    """보관본 폴더(파일이 하나라도 있는 것)가 있으면 그 경로를, 없거나 읽을 수 없으면 None 을 돌려준다."""
    folder = project_dir(project_number)
    if folder is None:
        return None
    try:
        if not folder.is_dir():
            return None
        with os.scandir(folder) as entries:
            return folder if any(not entry.name.startswith(HIDDEN_PREFIXES) for entry in entries) else None
    except OSError as exc:
        logger.warning("archive: cannot read %s (%s)", folder, exc)
        return None


def archived_at(project_number):
    """보관본이 만들어진(마지막 점검이 끝난) 시각 문자열. 기록이 없는 예전 보관본은 빈 문자열."""
    folder = project_dir(project_number)
    if folder is None:
        return ""
    try:
        data = json.loads((folder / MARKER_NAME).read_text(encoding="utf-8"))
        return str(data.get("archived_at") or "")
    except (OSError, ValueError):
        return ""


def write_marker(folder, **extra):
    """보관 폴더에 완성 시각을 적는다(교체 직전, 임시 폴더 안에서 호출)."""
    payload = {"archived_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), **extra}
    (Path(folder) / MARKER_NAME).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _meta(rel, size):
    return {
        "fileName": rel.rsplit("/", 1)[-1],
        "fileOID": rel,
        "storageFileID": rel,
        "fileSize": size,
    }


class _LocalResponse:
    """ECM blob_stream 응답과 같은 모양(iter_content / close)의 로컬 파일 읽기."""

    def __init__(self, path):
        self._handle = open(path, "rb")

    def iter_content(self, chunk_size=1024 * 1024):
        while True:
            data = self._handle.read(chunk_size)
            if not data:
                return
            yield data

    def close(self):
        self._handle.close()


class ArchiveClient:
    """프로젝트 보관 폴더 하나 안에서만 움직이는 ECM 클라이언트 흉내. oid/storageFileID 는 보관 폴더 기준 상대 경로다."""

    def __init__(self, project_number):
        folder = project_dir(project_number)
        if folder is None:
            raise ArchiveError("보관 폴더가 설정되지 않았습니다.")
        self.project_number = project_number
        self.root = folder

    # ----- 경로 안전 -----
    def resolve(self, rel):
        """상대 경로를 보관 폴더 안의 실제 경로로. 폴더 밖(.., 절대 경로, 링크로 나간 경로)이면 오류."""
        text = unicodedata.normalize("NFC", str(rel or "")).replace("\\", "/")
        parts = [part for part in text.split("/") if part]
        if any(part in (".", "..") for part in parts) or (len(text) > 1 and text[1] == ":"):
            raise ArchiveError("올바르지 않은 경로입니다.")
        if any(part.startswith(HIDDEN_PREFIXES) for part in parts):
            raise ArchiveError("열 수 없는 경로입니다.")
        path = self.root.joinpath(*parts)
        try:
            real_root = os.path.realpath(self.root)
            real_path = os.path.realpath(path)
            if os.path.commonpath([real_root, real_path]) != real_root:
                raise ArchiveError("보관 폴더 밖의 경로는 열 수 없습니다.")
        except ValueError as exc:
            raise ArchiveError("올바르지 않은 경로입니다.") from exc
        return path

    def login(self):  # ECM 클라이언트와 모양을 맞춘다
        return None

    # ----- ECM 클라이언트와 같은 메서드 -----
    def folder_contents(self, oid):
        folder = self.resolve(oid)
        base = unicodedata.normalize("NFC", str(oid or "")).replace("\\", "/").strip("/")
        folders, files = [], []
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    name = unicodedata.normalize("NFC", entry.name)
                    if name.startswith(HIDDEN_PREFIXES):
                        continue
                    rel = f"{base}/{name}" if base else name
                    if entry.is_dir(follow_symlinks=False):
                        folders.append({"name": name, "oid": rel})
                    elif entry.is_file(follow_symlinks=False):
                        files.append(_meta(rel, entry.stat().st_size))
        except OSError as exc:
            raise ArchiveError(f"보관 폴더를 읽지 못했습니다: {exc}") from exc
        return {"folders": folders, "files": files}

    def walk_files(self, oid, _rel=None):
        rel = list(_rel or [])
        contents = self.folder_contents(oid)
        for meta in contents["files"]:
            yield rel, meta
        for child in contents["folders"]:
            yield from self.walk_files(child["oid"], rel + [child["name"]])

    def blob_stream(self, meta):
        path = self.resolve(meta.get("storageFileID", ""))
        try:
            return _LocalResponse(path)
        except OSError as exc:
            raise ArchiveError(f"보관된 파일을 열지 못했습니다: {exc}") from exc

    def file_path(self, rel):
        """보관 폴더 안의 실제 파일 경로(zip 을 직접 열어 중간만 읽을 때 쓴다)."""
        return self.resolve(rel)
