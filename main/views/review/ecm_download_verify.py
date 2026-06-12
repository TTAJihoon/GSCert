"""
다운로드 파일 확인 (9단계).

다운로드된 폴더에서 파일 존재 여부, 개수, 기본 무결성을 확인한다.
zip 검사가 아니라 개별 파일 다운로드 확인이다.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

logger = logging.getLogger("main.views.review.ecm_download_verify")


@dataclass
class FileInfo:
    name: str
    path: str
    size: int
    extension: str
    modified_at: datetime | None = None


@dataclass
class DownloadVerifyResult:
    success: bool
    download_dir: str = ""
    file_count: int = 0
    total_size: int = 0
    files: List[FileInfo] = field(default_factory=list)
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    has_project_number_files: bool = False


def verify_downloaded_files(
    download_dir: str,
    project_number: str,
    min_file_count: int = 1,
) -> DownloadVerifyResult:
    """다운로드 폴더의 파일들을 확인한다.

    확인 항목:
    1. 폴더가 존재하는지
    2. 파일이 1개 이상 있는지
    3. 0바이트 파일이 없는지
    4. 프로젝트번호를 포함하는 파일이 있는지
    """
    if not os.path.isdir(download_dir):
        return DownloadVerifyResult(
            success=False,
            download_dir=download_dir,
            error_message=f"다운로드 폴더가 존재하지 않습니다: {download_dir}",
        )

    files = []
    empty_files = []
    has_project_number = False

    for root, _dirs, filenames in os.walk(download_dir):
        for filename in filenames:
            path = os.path.join(root, filename)
            stat = os.stat(path)
            ext = os.path.splitext(filename)[1].lower()
            rel_name = os.path.relpath(path, download_dir).replace(os.sep, "/")
            fi = FileInfo(
                name=filename,
                path=path,
                size=stat.st_size,
                extension=ext,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
            )
            files.append(fi)

            if stat.st_size == 0:
                empty_files.append(rel_name)

            if project_number in rel_name:
                has_project_number = True

    file_count = len(files)
    total_size = sum(f.size for f in files)

    if file_count < min_file_count:
        return DownloadVerifyResult(
            success=False,
            download_dir=download_dir,
            file_count=file_count,
            total_size=total_size,
            files=files,
            error_message=f"다운로드된 파일이 부족합니다: {file_count}개 (최소 {min_file_count}개)",
        )

    if empty_files:
        return DownloadVerifyResult(
            success=False,
            download_dir=download_dir,
            file_count=file_count,
            total_size=total_size,
            files=files,
            error_message="0 byte 다운로드 파일이 있습니다: " + ", ".join(empty_files[:5]),
            has_project_number_files=has_project_number,
        )

    warnings = []
    if not has_project_number:
        warnings.append("프로젝트 번호가 파일명에 포함된 파일을 찾지 못했습니다.")
        logger.warning(
            "프로젝트 번호가 파일명에 없는 다운로드 결과: %s (%s)",
            project_number,
            download_dir,
        )

    return DownloadVerifyResult(
        success=True,
        download_dir=download_dir,
        file_count=file_count,
        total_size=total_size,
        files=files,
        warnings=warnings,
        has_project_number_files=has_project_number,
    )


def summarize_files(result: DownloadVerifyResult) -> dict:
    """확인 결과를 DB 저장용 dict로 변환한다."""
    ext_counts = {}
    for f in result.files:
        ext = f.extension or "(확장자 없음)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    return {
        "file_count": result.file_count,
        "total_size_bytes": result.total_size,
        "total_size_mb": round(result.total_size / (1024 * 1024), 2),
        "has_project_number_files": result.has_project_number_files,
        "extensions": ext_counts,
        "file_names": [f.name for f in result.files],
        "empty_files": [f.name for f in result.files if f.size == 0],
        "warnings": result.warnings,
    }
