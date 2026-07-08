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

# #1(성적서)과 #2(전체)를 서로 다른 폴더에 저장해 캐시/ZIP 혼입을 원천 차단한다.
#   - 전체(#2): <base>/<시험번호>            → ZIP 으로 서빙(download_report)
#   - 성적서(#1): <base>/__report/<시험번호>  → 파일 그대로 서빙(download_report_document)
_DOC_SUBDIR = "__report"


def _report_base() -> str:
    return getattr(settings, "AGENT_REPORT_BASE_DIR", r"C:\Users\Administrator\report")


def all_dir(test_no: str) -> Path:
    """#2 전체 다운로드 저장 폴더(ZIP 서빙 대상)."""
    return Path(_report_base()) / unicodedata.normalize("NFC", str(test_no or "").strip())


def doc_dir(test_no: str) -> Path:
    """#1 성적서 저장 폴더(파일 그대로 서빙 대상)."""
    return Path(_report_base()) / _DOC_SUBDIR / unicodedata.normalize("NFC", str(test_no or "").strip())


def report_cache_valid(test_no: str, report_only: bool) -> bool:
    """해당 범위 전용 폴더에 파일이 이미 있으면 True(ECM 재접속 불필요).

    범위별 폴더가 분리돼 있어 #1/#2 간 캐시 혼입이 발생하지 않는다.
    """
    if not str(test_no or "").strip():
        return False
    folder = doc_dir(test_no) if report_only else all_dir(test_no)
    return folder.is_dir() and any(p.is_file() for p in folder.rglob("*"))


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


def download_full_project_documents(
    test_no: str,
    cert_date: str = "",
    *,
    dest_base: str | None = None,
) -> dict:
    """'전체 다운로드' 버튼: 프로젝트가 속한 센터 ECM 에 접속해 프로젝트 폴더 전체를 받는다.

    센터는 점검과 동일한 reference_project(센터별 PL 목록) 기준으로 해석한다. 폴더 탐색은
    점검 워커와 같은 `find_project_folder`({연도} 시험서비스 → GS 포함 폴더 → 프로젝트번호 폴더)
    를 재사용하고, 그 폴더 아래 모든 파일을 상대경로 그대로 report\\<시험번호> 에 받아
    (이후 download_report 가 ZIP 으로 전달) 저장한다.
    """
    from main.views.review.artifact_source import verify_downloaded_bytes
    from main.views.review.ecm_http_client import build_client

    center, project = _resolve_project_center(test_no)
    if not center:
        raise RuntimeError(f"{test_no} 의 센터를 확인할 수 없습니다(reference_project 미등록).")
    proj_cert_date = (project.get("cert_date") if project else "") or cert_date

    client = build_client(center)
    client.login()

    # #2 전용 경로: 분당은 {연도} 시험서비스 → (GS+1등급) → 프로젝트,
    # 상암/영남은 그 앞에 '상암'/'영남' 센터 폴더 단계를 더 탄다.
    folder = client.find_full_project_folder(test_no, proj_cert_date, center)
    if not folder or not folder.get("oid"):
        raise RuntimeError(f"{center} ECM 에서 프로젝트 폴더를 찾지 못했습니다: {test_no}")

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

    return {"download_dir": str(base), "doc_count": count, "center": center}
