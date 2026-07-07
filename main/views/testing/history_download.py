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

from django.conf import settings

# 캐시된 report 폴더가 어떤 범위(scope)로 받아졌는지 기록하는 마커 파일.
_SCOPE_MARKER = ".scope"


def _report_base() -> str:
    return getattr(settings, "AGENT_REPORT_BASE_DIR", r"C:\Users\Administrator\report")


def _scope_value(report_only: bool) -> str:
    return "report" if report_only else "all"


def report_cache_valid(test_no: str, report_only: bool) -> bool:
    """report 폴더에 요청한 범위(scope)와 일치하는 파일이 이미 있으면 True(ECM 재접속 불필요)."""
    name = unicodedata.normalize("NFC", str(test_no or "")).strip()
    if not name:
        return False
    folder = Path(_report_base()) / name
    if not folder.is_dir():
        return False
    has_file = any(p.is_file() and p.name != _SCOPE_MARKER for p in folder.rglob("*"))
    if not has_file:
        return False
    marker = folder / _SCOPE_MARKER
    cached_scope = marker.read_text(encoding="utf-8").strip() if marker.exists() else "report"
    return cached_scope == _scope_value(report_only)


def download_history_documents(
    cert_date: str,
    test_no: str,
    *,
    report_only: bool = True,
    center: str = "bundang",
    dest_base: str | None = None,
) -> dict:
    """인증위원회 트리에서 시험번호 폴더를 찾아 문서를 report 폴더로 다운로드한다.

    report_only=True(기본): 시험성적서 Word 파일만. False: 전체 파일.
    반환: {"download_dir", "doc_count"}. 실패 시 RuntimeError.
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

    name = unicodedata.normalize("NFC", str(test_no))
    base = Path(dest_base or _report_base()) / name
    # 요청 범위와 정확히 일치하도록 기존 폴더를 비우고 새로 받는다.
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)

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

    (base / _SCOPE_MARKER).write_text(_scope_value(report_only), encoding="utf-8")
    return {"download_dir": str(base), "doc_count": len(selected)}
