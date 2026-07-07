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
import re
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
        from main.utils.ecm_agent_lock import async_ecm_agent_lock
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

        # ECM 단일 Windows 에이전트 동시 사용 방지 락은 ECM 고유 정책이므로 이 어댑터가
        # 소유한다(로컬 등 다른 source 는 락이 필요 없다).
        lock_timeout = getattr(settings, "ECM_AGENT_LOCK_TIMEOUT_SECONDS", 600)
        async with async_ecm_agent_lock(timeout_seconds=lock_timeout):
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


# 무결성 검증(결정 8): 확장자별 매직바이트. 압축 기반 오피스 포맷은 모두 PK.
_MAGIC_BYTES = {
    "zip": b"PK",
    "xlsx": b"PK",
    "xlsm": b"PK",
    "docx": b"PK",
    "docm": b"PK",
    "pptx": b"PK",
    "hwpx": b"PK",
    "pdf": b"%PDF",
}


def verify_downloaded_bytes(data: bytes, file_name: str, expected_size: int) -> str:
    """다운로드 바이트 무결성 검증. 문제 없으면 "", 있으면 사유 문자열(결정 8).

    - 빈 응답 / 잘림 탐지: expected_size(API 보고값)와 실제 바이트 수 대조.
    - 매직바이트: 확장자가 압축/서명 포맷이면 시작 바이트가 부합하는지 확인.
    """
    if not data:
        return "빈 파일(0바이트) 응답"
    if expected_size and len(data) != int(expected_size):
        return f"파일 크기 불일치(기대 {expected_size}, 실제 {len(data)})"
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    magic = _MAGIC_BYTES.get(ext)
    if magic and not data.startswith(magic):
        return f"매직바이트 불일치(.{ext} 인데 {data[:4]!r})"
    return ""


class HttpEcmArtifactSource:
    """서버측 HTTP 직접 호출(`requests`)로 Destiny ECM 산출물을 받아오는 source.

    Playwright/pywinauto 없이 `ecm_http_client.DestinyECM` 만으로 로그인→프로젝트 폴더
    탐색→재귀 순회→다운로드를 수행한다. 팝업/저장대화상자/에이전트 락이 없다.
    받은 파일은 기존 Playwright 방식과 동일한 폴더 레이아웃
    `AGENT_DOWNLOAD_BASE_DIR/<NFC project_number>/<NFC relative_path>/...`
    으로 서버 디스크에 떨어뜨리므로, 이후 검증·보관·점검 파이프라인은 그대로 동작한다.

    설계 근거: main/docs/34_http_ecm_source_decisions.md(결정 2·6·7·8·9), 33_artifact_source_boundary.md
    """

    name = "ecm-http"

    def __init__(self, *, client_factory: Callable[[str], Any] | None = None):
        # client_factory(center_code) -> DestinyECM. 테스트에서 mock 주입 지점.
        self._client_factory = client_factory
        self._clients: dict[str, Any] = {}

    async def open(self) -> None:
        # 로그인은 프로젝트별 center_code 를 알아야 하므로 fetch 시점에 lazy 로그인한다.
        # (job 내 같은 센터 클라이언트/세션은 재사용 — 결정 2)
        return None

    async def close(self) -> None:
        self._clients.clear()

    def _factory(self):
        if self._client_factory is not None:
            return self._client_factory
        from main.views.review.ecm_http_client import build_client

        return build_client

    async def _client_for(self, center_code: str):
        key = center_code or ""
        client = self._clients.get(key)
        if client is None:
            factory = self._factory()
            client = await asyncio.to_thread(factory, center_code)
            await asyncio.to_thread(client.login)
            self._clients[key] = client
        return client

    async def fetch(self, project, *, on_progress, is_canceled) -> FetchResult:
        base = Path(getattr(settings, "AGENT_DOWNLOAD_BASE_DIR"))
        project_number = unicodedata.normalize("NFC", project.project_number)
        download_dir = base / project_number

        if await is_canceled():
            raise JobCanceledError()

        center_code = getattr(project, "center_code", "") or ""
        row = getattr(project, "ecm_row_json", {}) or {}
        cert_date = str(row.get("cert_date") or "")
        grade = str(row.get("grade") or "")

        try:
            client = await self._client_for(center_code)
        except Exception as exc:  # 로그인/설정 실패
            return FetchResult(
                success=False,
                download_dir=str(download_dir),
                error_step="ECM 로그인",
                error_message=str(exc),
            )

        found = await asyncio.to_thread(
            client.find_project_folder, project.project_number, cert_date, grade
        )
        if not found or not found.get("oid"):
            return FetchResult(
                success=False,
                download_dir=str(download_dir),
                error_step="프로젝트 폴더 탐색",
                error_message=f"시험번호 {project.project_number} 에 해당하는 ECM 폴더를 찾지 못했습니다.",
            )

        state = {"folder_count": 0}

        try:
            await self._walk(
                client,
                found["oid"],
                relative_path=[],
                base=base,
                project_number=project_number,
                on_progress=on_progress,
                is_canceled=is_canceled,
                state=state,
            )
        except JobCanceledError:
            raise
        except _FetchFailed as exc:
            return FetchResult(
                success=False,
                download_dir=str(download_dir),
                downloaded_folder_count=state["folder_count"],
                error_step=exc.step,
                error_message=exc.message,
            )
        except Exception as exc:
            return FetchResult(
                success=False,
                download_dir=str(download_dir),
                downloaded_folder_count=state["folder_count"],
                error_step="ECM 다운로드",
                error_message=str(exc),
            )

        return FetchResult(
            success=True,
            download_dir=str(download_dir),
            downloaded_folder_count=state["folder_count"],
        )

    async def _walk(
        self,
        client,
        oid,
        *,
        relative_path,
        base,
        project_number,
        on_progress,
        is_canceled,
        state,
    ) -> None:
        if await is_canceled():
            raise JobCanceledError()

        contents = await asyncio.to_thread(client.folder_contents, oid)
        files = contents.get("files") or []
        folders = contents.get("folders") or []

        if files:
            await on_progress(list(relative_path), len(files))
            segments = [project_number] + [
                unicodedata.normalize("NFC", str(part)) for part in relative_path
            ]
            target_dir = base.joinpath(*segments)
            await asyncio.to_thread(lambda: target_dir.mkdir(parents=True, exist_ok=True))
            for meta in files:
                if await is_canceled():
                    raise JobCanceledError()
                await self._download_one(client, meta, target_dir)
            state["folder_count"] += 1

        for child in folders:
            child_oid = child.get("oid")
            if not child_oid:
                continue
            await self._walk(
                client,
                child_oid,
                relative_path=list(relative_path) + [child.get("name", "")],
                base=base,
                project_number=project_number,
                on_progress=on_progress,
                is_canceled=is_canceled,
                state=state,
            )

    async def _download_one(self, client, meta, target_dir: Path) -> None:
        file_name = unicodedata.normalize("NFC", str(meta.get("fileName") or ""))
        expected_size = int(meta.get("fileSize") or 0)
        safe_name = re.sub(r'[\\/:*?"<>|]', " ", file_name)
        dest = target_dir / safe_name

        # 다운로드 + 무결성 검증. 실패 시 1회 재다운로드(결정 8).
        last_reason = ""
        for _attempt in range(2):
            data = await asyncio.to_thread(client.download_bytes, meta)
            last_reason = verify_downloaded_bytes(data, file_name, expected_size)
            if not last_reason:
                await asyncio.to_thread(self._write_bytes, dest, data)
                return
        raise _FetchFailed("무결성 검증", f"{file_name}: {last_reason}")

    @staticmethod
    def _write_bytes(dest: Path, data: bytes) -> None:
        tmp = dest.with_name(dest.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)


class _FetchFailed(Exception):
    """_walk 내부에서 발생한 복구 불가 실패를 fetch 로 전달하는 내부 신호."""

    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step
        self.message = message


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


def build_artifact_source(
    name: str = "ecm",
    *,
    headless: bool = True,
    source_root: str | None = None,
) -> ArtifactSource:
    """source 이름으로 구현체를 생성한다(기본: ecm).

    - ecm: 현 운영 기본. Playwright + Windows Agent.
    - ecm-http: 서버측 HTTP 직접연동(requests). Playwright/pywinauto 불필요. 자격증명/
      root OID 는 센터 정의(settings) 에서 읽는다. 안정화 후 기본값으로 승격 예정.
    - local: `source_root/<프로젝트번호>` 를 다운로드 폴더로 복사(다른 저장소 연결 첫 구현
      이자 fake-live 테스트용). source_root 미지정 시 settings.LOCAL_ARTIFACT_SOURCE_ROOT 사용.
    """
    key = (name or "ecm").strip().lower()
    if key == "ecm":
        return EcmArtifactSource(headless=headless)
    if key == "ecm-http":
        return HttpEcmArtifactSource()
    if key == "local":
        return LocalFolderArtifactSource(source_root=source_root)
    raise ValueError(f"알 수 없는 artifact source: {name}")
