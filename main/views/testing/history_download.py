"""시험 이력 '문서 다운로드'의 HTTP 직접연동 구현.

기존 Playwright + pywinauto('폴더 찾아보기' 팝업) 방식을 대체한다. 인증위원회 트리에서
시험번호 폴더를 찾아 기본적으로 **시험성적서 Word 파일만**(옵션: 전체) 서버 report 폴더에
내려받고, 이후 ZIP 전달은 기존 `history_report.download_report` 가 그대로 처리한다.

인증위원회(GS인증심의위원회)는 분당 ECM(210.104.181.10)에 있으므로 center=bundang 로 접속한다.
자격증명은 ECM_USERNAME_BUNDANG/ECM_PASSWORD_BUNDANG 환경변수에서 읽는다.
"""

from __future__ import annotations

import shutil
import unicodedata
from pathlib import Path
import zipfile

from django.conf import settings

# #1(성적서)과 #2(전체)를 서로 다른 폴더에 저장해 캐시/ZIP 혼입을 원천 차단한다.
#   - 전체(#2): <base>/<시험번호>            → ZIP 으로 서빙(download_report)
#   - 성적서(#1): <base>/__report/<시험번호>  → 파일 그대로 서빙(download_report_document)
_DOC_SUBDIR = "__report"


def _report_base() -> str:
    return getattr(settings, "AGENT_REPORT_BASE_DIR", r"C:\Users\Administrator\report")


def all_dir(test_no: str) -> Path:
    """#2 전체 다운로드 저장 폴더(원본 파일)."""
    return Path(_report_base()) / unicodedata.normalize("NFC", str(test_no or "").strip())


def zip_path(test_no: str) -> Path:
    """#2 전체 다운로드용으로 미리 만들어 둔 ZIP 경로(서빙 대상). all_dir 밖에 둔다."""
    name = unicodedata.normalize("NFC", str(test_no or "").strip())
    return Path(_report_base()) / "__zip" / (name + ".zip")


def doc_dir(test_no: str) -> Path:
    """#1 성적서 저장 폴더(파일 그대로 서빙 대상)."""
    return Path(_report_base()) / _DOC_SUBDIR / unicodedata.normalize("NFC", str(test_no or "").strip())


def download_history_documents(
    cert_date: str,
    test_no: str,
    *,
    report_only: bool = True,
    center: str = "bundang",
    dest_base: str | None = None,
) -> dict:
    """인증위원회 트리에서 시험번호 폴더를 찾아 문서를 report 폴더로 다운로드한다.

    report_only=True(기본): 시험성적서 Word 파일만(성적서 폴더에 저장, 파일 그대로 서빙).
    report_only=False: 인증위원회 트리 전체 파일.
    반환: {"download_dir", "doc_count", "files"}. 실패 시 RuntimeError.
    """
    from main.views.review.artifact_source import verify_downloaded_bytes
    from main.views.review.ecm_http_client import build_client

    client = build_client(center)
    client.login()

    folder = client.find_committee_test_folder(test_no, cert_date)
    if not folder or not folder.get("oid"):
        raise RuntimeError(
            f"인증위원회 트리에서 시험번호 {test_no}(인증일자 {cert_date}) 폴더를 찾지 못했습니다."
        )

    files = client.files(folder["oid"])
    selected = client.select_report_documents(files, report_only=report_only)
    if not selected:
        if report_only:
            raise RuntimeError(f"{test_no} 폴더에서 시험성적서(Word) 문서를 찾지 못했습니다.")
        raise RuntimeError(f"{test_no} 폴더에 다운로드할 문서가 없습니다.")

    if dest_base is not None:
        base = Path(dest_base) / unicodedata.normalize("NFC", str(test_no))
    else:
        base = doc_dir(test_no) if report_only else all_dir(test_no)
    # 요청 범위와 정확히 일치하도록 기존 폴더를 비우고 새로 받는다.
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

    saved = []
    for meta in selected:
        file_name = unicodedata.normalize("NFC", str(meta.get("fileName") or ""))
        expected_size = int(meta.get("fileSize") or 0)
        data = client.download_bytes(meta)
        reason = verify_downloaded_bytes(data, file_name, expected_size)
        if reason:
            # 1회 재시도
            data = client.download_bytes(meta)
            reason = verify_downloaded_bytes(data, file_name, expected_size)
            if reason:
                raise RuntimeError(f"무결성 검증 실패: {file_name} ({reason})")
        safe_name = file_name
        for ch in '\\/:*?"<>|':
            safe_name = safe_name.replace(ch, " ")
        dest = base / safe_name
        tmp = dest.with_name(dest.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        saved.append(safe_name)

    return {"download_dir": str(base), "doc_count": len(selected), "files": saved}


def _resolve_project_center(test_no: str):
    """점검과 동일한 방식으로 프로젝트가 속한 센터/기준정보를 찾는다.

    reference_project(센터별 PL 목록 기반, 공유 reference DB)에는 전 센터 데이터가 있고
    프로젝트번호는 센터 간 고유하므로, 전 센터를 훑어 첫 매치를 사용한다.
    반환: (center_code, project_dict) 또는 (None, None).
    """
    from main.views.review.ecm_download_review_centers import center_choices
    from main.views.review.ecm_reference_db import get_projects_by_numbers

    number = unicodedata.normalize("NFC", str(test_no or "")).strip()
    for choice in center_choices():
        code = choice["code"]
        try:
            payload = get_projects_by_numbers([number], center_code=code)
        except Exception:
            continue
        if payload and payload[0]:
            return code, payload[0]
    return None, None


def _find_full_project_source(test_no: str, cert_date: str = ""):
    from main.views.review.ecm_http_client import build_client

    resolved_center, project = _resolve_project_center(test_no)
    proj_cert_date = (project.get("cert_date") if project else "") or cert_date

    # 시도 순서: 해석된 센터를 맨 앞에, 이어서 분당→상암→영남 폴백(중복 제거).
    order = []
    if resolved_center:
        order.append(resolved_center)
    for c in ("bundang", "sangam", "yeongnam"):
        if c not in order:
            order.append(c)

    errors = []
    for candidate in order:
        try:
            client = build_client(candidate)
            client.login()
            folder = client.find_full_project_folder(test_no, proj_cert_date, candidate)
        except Exception as exc:  # 자격증명 없음/네트워크/로그인 실패 → 다음 센터 시도
            errors.append(f"{candidate}: {exc}")
            continue
        if folder and folder.get("oid"):
            return client, candidate, folder

    detail = ("; ".join(errors)) if errors else "해당 없음"
    raise RuntimeError(
        f"어느 센터 ECM 에서도 프로젝트 폴더를 찾지 못했습니다: {test_no} (시도: {detail})"
    )


class _StreamingZipSink:
    """zipfile 이 쓰는 bytes 를 StreamingHttpResponse 로 흘려보내기 위한 sink."""

    def __init__(self):
        self._chunks = []

    def write(self, data):
        if data:
            self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        return None

    def tell(self):
        raise OSError("stream is not seekable")

    def seek(self, *_args):
        raise OSError("stream is not seekable")

    def seekable(self):
        return False

    def drain(self):
        chunks = self._chunks
        self._chunks = []
        for chunk in chunks:
            if chunk:
                yield chunk


def _safe_zip_part(value):
    part = unicodedata.normalize("NFC", str(value or "")).strip()
    for ch in '\\/:*?"<>|':
        part = part.replace(ch, " ")
    part = part.strip(" .")
    return part or "_"


def _zip_arcname(rel, file_name):
    parts = [_safe_zip_part(part) for part in rel or []]
    parts.append(_safe_zip_part(file_name))
    return "/".join(parts)


def _unique_arcname(arcname, seen):
    count = seen.get(arcname, 0)
    seen[arcname] = count + 1
    if count == 0:
        return arcname
    path = Path(arcname)
    stem = path.stem
    suffix = path.suffix
    parent = path.parent.as_posix()
    renamed = f"{stem} ({count + 1}){suffix}"
    return renamed if parent == "." else f"{parent}/{renamed}"


def _single_error_zip(message):
    sink = _StreamingZipSink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("다운로드 오류.txt", str(message or "문서 다운로드 실패"))
        yield from sink.drain()
    yield from sink.drain()


def iter_full_project_documents_zip(test_no: str, cert_date: str = ""):
    """프로젝트 전체 문서를 서버 디스크 ZIP 선생성 없이 바로 ZIP 스트리밍한다.

    새 화면에서 전체 폴더 다운로드 기능을 재사용할 때는 POST로 준비 완료 JSON을
    기다리지 말고 이 스트림을 반환하는 GET attachment 엔드포인트를 사용한다.
    """
    from main.views.review.artifact_source import verify_downloaded_bytes

    try:
        client, _center, folder = _find_full_project_source(test_no, cert_date)
        items = list(client.walk_files(folder["oid"]))
        if not items:
            raise RuntimeError(f"{test_no} 프로젝트 폴더에 파일이 없습니다.")
    except Exception as exc:
        yield from _single_error_zip(exc)
        return

    sink = _StreamingZipSink()
    seen = {}
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, meta in items:
            file_name = unicodedata.normalize("NFC", str(meta.get("fileName") or "download"))
            arcname = _unique_arcname(_zip_arcname(rel, file_name), seen)
            info = zipfile.ZipInfo(arcname)
            info.compress_type = zipfile.ZIP_DEFLATED
            download_error = None
            with zf.open(info, "w") as entry:
                # 파일 내용을 받기 전 ZIP 엔트리 헤더를 먼저 보내 브라우저 다운로드를 시작시킨다.
                yield from sink.drain()
                expected_size = int(meta.get("fileSize") or 0)
                try:
                    data = client.download_bytes(meta)
                    reason = verify_downloaded_bytes(data, file_name, expected_size)
                    if reason:
                        data = client.download_bytes(meta)
                        reason = verify_downloaded_bytes(data, file_name, expected_size)
                        if reason:
                            raise RuntimeError(f"무결성 검증 실패: {file_name} ({reason})")
                    entry.write(data)
                except Exception as exc:
                    download_error = exc
                yield from sink.drain()
            yield from sink.drain()
            if download_error is not None:
                zf.writestr(
                    "다운로드 오류.txt",
                    f"{arcname} 다운로드 중 오류가 발생했습니다.\n{download_error}",
                )
                yield from sink.drain()
                break
    yield from sink.drain()


def download_full_project_documents(
    test_no: str,
    cert_date: str = "",
    *,
    dest_base: str | None = None,
) -> dict:
    """'전체 다운로드' 버튼: 프로젝트가 속한 센터 ECM 에 접속해 프로젝트 폴더 전체를 받는다.

    센터 결정:
    1) reference_project(센터별 PL 목록)로 우선 해석해 그 센터를 먼저 시도한다.
    2) 그래도 못 찾으면(미등록/오분류 포함) 분당 → 상암 → 영남 순으로 각 센터 ECM 을
       직접 탐색(find_full_project_folder)해 프로젝트 폴더가 있는 첫 센터를 사용한다.
    폴더 탐색은 #2 전용 `find_full_project_folder`(분당: {연도} 시험서비스 → GS·1등급 →
    프로젝트 / 상암·영남: '상암'|'영남' 폴더 → {연도} 시험서비스 → GS·1등급 → 프로젝트)를
    쓰고, 그 폴더 아래 모든 파일을 상대경로 그대로 report\\<시험번호> 에 받아 ZIP 으로 전달한다.
    """
    from main.views.review.artifact_source import verify_downloaded_bytes

    client, center, folder = _find_full_project_source(test_no, cert_date)

    items = list(client.walk_files(folder["oid"]))
    if not items:
        raise RuntimeError(f"{test_no} 프로젝트 폴더에 파일이 없습니다.")

    if dest_base is not None:
        base = Path(dest_base) / unicodedata.normalize("NFC", str(test_no))
    else:
        base = all_dir(test_no)
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

    count = 0
    for rel, meta in items:
        file_name = unicodedata.normalize("NFC", str(meta.get("fileName") or ""))
        expected_size = int(meta.get("fileSize") or 0)
        data = client.download_bytes(meta)
        reason = verify_downloaded_bytes(data, file_name, expected_size)
        if reason:
            data = client.download_bytes(meta)
            reason = verify_downloaded_bytes(data, file_name, expected_size)
            if reason:
                raise RuntimeError(f"무결성 검증 실패: {file_name} ({reason})")
        target_dir = base.joinpath(*[unicodedata.normalize("NFC", str(p)) for p in rel])
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = file_name
        for ch in '\\/:*?"<>|':
            safe_name = safe_name.replace(ch, " ")
        dest = target_dir / safe_name
        tmp = dest.with_name(dest.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
        count += 1

    # WS(로딩 표시) 단계에서 ZIP 을 미리 만들어 둔다. 이렇게 하면 이후 브라우저의
    # /download/ GET 은 완성된 ZIP 을 즉시 스트리밍(FileResponse)하므로, 로딩이 사라진 뒤
    # 다운로드가 시작되기까지의 압축 지연이 사라진다.
    zp = zip_path(test_no)
    zp.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = zp.with_name(zp.name + ".part")
    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(base.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=p.relative_to(base).as_posix())
    tmp_zip.replace(zp)

    return {"download_dir": str(base), "doc_count": count, "center": center, "zip_path": str(zp)}
