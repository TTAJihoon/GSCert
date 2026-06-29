"""산출물 획득 source 추상화.

워커는 "프로젝트 → 로컬 다운로드 폴더"를 만들어 주는 source 에만 의존한다.
ECM(Playwright + Windows Agent 팝업)은 그 한 구현일 뿐이며, 추후 로컬 폴더나
다른 저장소로 갈아끼울 때 이 인터페이스를 구현한 새 source 만 붙이면 된다.

경계:
- source-specific(이 모듈): 어떻게 받아오는가(ECM 탐색/팝업, 로컬 복사 등).
- source-agnostic(워커): 받은 *로컬 폴더*에 대한 검증·보관·점검·상태 전이·정리.

fetch() 는 산출물을 로컬 다운로드 폴더에 만들고 그 경로와 성패를 FetchResult 로 돌려준다.
진행 보고/취소 확인은 Django 모델을 모르도록 콜백(on_progress/is_canceled)으로 주입받는다.
"""

from __future__ import annotations

import asyncio
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from django.conf import settings


# 진행 보고: (relative_path, doc_count) → 워커가 _mark_project 로 매핑.
ProgressHook = Callable[[list], Awaitable[Any]]
# 취소 확인: True 면 fetch 를 즉시 중단해야 한다.
CanceledHook = Callable[[], Awaitable[bool]]


class JobCanceledError(Exception):
    """fetch 도중 작업이 강제 종료(취소)되었음을 알리는 신호."""


@dataclass
class FetchResult:
    """source 가 산출물을 로컬에 받은 결과(어느 source 든 동일 형태)."""

    success: bool
    download_dir: str = ""
    downloaded_folder_count: int = 0
    error_step: str = ""
    error_message: str = ""


class ArtifactSource(Protocol):
    """프로젝트 산출물을 로컬 다운로드 폴더로 가져오는 source 계약.

    - open(): 작업(job) 단위 준비(예: 브라우저 launch). 1회.
    - fetch(project): 프로젝트 1건을 로컬 폴더로 받아 FetchResult 반환.
    - close(): 작업 단위 정리(예: 브라우저 close). 1회.
    """

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def fetch(
        self,
        project: Any,
        *,
        on_progress: ProgressHook,
        is_canceled: CanceledHook,
    ) -> FetchResult: ...


class EcmArtifactSource:
    """ECM 웹(Playwright) + Windows Agent 팝업(pywinauto)으로 받아오는 source."""

    name = "ecm"

    def __init__(self, *, headless: bool = True):
        self._headless = headless
        self._browser = None

    async def open(self) -> None:
        from main.views.review.ecm_download import launch_browser

        self._browser = await launch_browser(headless=self._headless)

    async def close(self) -> None:
        if self._browser is not None:
            from main.views.review.ecm_download import close_browser

            await close_browser(self._browser)
            self._browser = None

    async def fetch(self, project, *, on_progress, is_canceled) -> FetchResult:
        from main.views.review.ecm_agent_popup import handle_folder_popup_and_download
        from main.views.review.ecm_download import run_ecm_recursive_downloads

        async def _download_folder(relative_path, doc_count):
            # 폴더별 다운로드 직전마다 취소를 확인해, 한 프로젝트가 여러 폴더를
            # 받는 도중에도 즉시 멈춘다.
            if await is_canceled():
                raise JobCanceledError()
            await on_progress(relative_path, doc_count)
            return await asyncio.to_thread(
                handle_folder_popup_and_download,
                project.project_number,
                str(project.job_id),
                2,
                relative_path,
                project.center_code,
            )

        result = await run_ecm_recursive_downloads(
            self._browser,
            project.project_number,
            center_code=project.center_code,
            download_callback=_download_folder,
        )
        return FetchResult(
            success=result.success,
            download_dir=result.download_dir,
            downloaded_folder_count=result.downloaded_folder_count,
            error_step=result.error_step,
            error_message=result.error_message,
        )


class LocalFolderArtifactSource:
    """로컬(또는 임의) 폴더에서 산출물을 복사해 오는 source.

    `source_root/<프로젝트번호>` 의 내용을 다운로드 폴더(AGENT_DOWNLOAD_BASE_DIR)/<프로젝트번호>
    로 복사한다. ECM 대신 다른 저장소를 붙일 때의 첫 구현이자, ECM 없이 워커 흐름을
    돌리는 테스트 더블(fake-live)로도 쓴다.
    """

    name = "local"

    def __init__(self, *, source_root: str | None = None):
        self._source_root = source_root

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def fetch(self, project, *, on_progress, is_canceled) -> FetchResult:
        if await is_canceled():
            raise JobCanceledError()
        return await asyncio.to_thread(self._copy_project, project)

    def _copy_project(self, project) -> FetchResult:
        base = Path(getattr(settings, "AGENT_DOWNLOAD_BASE_DIR"))
        root = Path(self._source_root or getattr(settings, "LOCAL_ARTIFACT_SOURCE_ROOT", ""))
        project_number = unicodedata.normalize("NFC", project.project_number)
        src = root / project_number
        dst = base / project_number
        if not src.is_dir():
            return FetchResult(
                success=False,
                download_dir=str(dst),
                error_step="로컬 폴더 확인",
                error_message=f"원본 폴더가 없습니다: {src}",
            )
        dst.mkdir(parents=True, exist_ok=True)
        folder_count = 0
        for item in src.iterdir():
            target = dst / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
                folder_count += 1
            else:
                shutil.copy2(item, target)
        return FetchResult(
            success=True,
            download_dir=str(dst),
            downloaded_folder_count=folder_count or 1,
        )


def build_artifact_source(name: str = "ecm", *, headless: bool = True, **kwargs) -> ArtifactSource:
    """source 이름으로 구현체를 생성한다(기본: ecm)."""
    key = (name or "ecm").strip().lower()
    if key == "ecm":
        return EcmArtifactSource(headless=headless)
    if key == "local":
        return LocalFolderArtifactSource(**kwargs)
    raise ValueError(f"알 수 없는 artifact source: {name}")
