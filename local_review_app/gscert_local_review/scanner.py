from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    name: str
    extension: str
    size_bytes: int


@dataclass(frozen=True)
class DirectoryRecord:
    relative_path: str
    name: str


@dataclass(frozen=True)
class FolderScan:
    folder: Path
    files: list[FileRecord]
    directories: list[DirectoryRecord] | None = None

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_size_bytes(self) -> int:
        return sum(file.size_bytes for file in self.files)

    @property
    def total_size_mb(self) -> float:
        return round(self.total_size_bytes / (1024 * 1024), 2)

    @property
    def directory_count(self) -> int:
        return len(self.directories or [])


def scan_folder(
    folder: Path,
    progress_cb: Callable[[int], None] | None = None,
) -> FolderScan:
    records: list[FileRecord] = []
    directories: list[DirectoryRecord] = []
    for path in folder.rglob("*"):
        if path.is_dir():
            directories.append(
                DirectoryRecord(
                    relative_path=path.relative_to(folder).as_posix(),
                    name=path.name,
                )
            )
            continue
        if not path.is_file():
            continue
        stat = path.stat()
        records.append(
            FileRecord(
                relative_path=path.relative_to(folder).as_posix(),
                name=path.name,
                extension=path.suffix.lower(),
                size_bytes=stat.st_size,
            )
        )
        if progress_cb is not None and len(records) % 25 == 0:
            progress_cb(len(records))
    records.sort(key=lambda file: (file.relative_path.count("/"), file.relative_path.lower()))
    directories.sort(key=lambda directory: (directory.relative_path.count("/"), directory.relative_path.lower()))
    if progress_cb is not None:
        progress_cb(len(records))
    return FolderScan(folder=folder, files=records, directories=directories)
