from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gscert_local_review.app_dashboard import main


def _self_check() -> int:
    import fitz  # noqa: F401
    import openpyxl  # noqa: F401
    import xlrd.compdoc  # noqa: F401
    from lxml import etree  # noqa: F401

    from gscert_local_review.cert_trust import build_ssl_context, bundled_cert_path
    from gscert_local_review.update_manager import bundled_app_version
    from gscert_review_core import engine

    if not bundled_cert_path().is_file() or build_ssl_context() is None:
        return 1

    print(f"[INFO] app version: {bundled_app_version() or '(none)'}")

    context = engine.build_context(project_number="SELF-CHECK")
    result = engine.evaluate_rules([], context, [])
    return 0 if result == [] else 1


def _debug_read_file(path: str) -> int:
    """특정 파일이 이 exe(패키징된 환경)에서 실제로 왜 안 읽히는지 확인하기 위한 진단용.
    예: GSCertLocalReviewDashboard.exe --debug-read-file "C:\\path\\to\\file.xls"
    """
    import traceback
    from pathlib import Path as _Path

    from gscert_review_core import engine

    file_path = _Path(path)
    if not file_path.is_file():
        print(f"[ERROR] 파일을 찾을 수 없습니다: {file_path}")
        return 1

    file_info = engine.FileInfo(
        name=file_path.name,
        path=str(file_path),
        size=file_path.stat().st_size,
        extension=file_path.suffix.lower(),
        modified_at=None,
    )
    print(f"[INFO] 파일: {file_info.path}")
    print(f"[INFO] 크기: {file_info.size} bytes, 확장자: {file_info.extension}")
    try:
        workbook = engine._read_excel_workbook(file_info)
    except Exception:
        print("[ERROR] _read_excel_workbook 실패:")
        traceback.print_exc()
        return 1
    print(f"[OK] 시트: {[sheet.name for sheet in workbook.sheets]}")
    return 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        raise SystemExit(_self_check())
    if "--debug-read-file" in sys.argv:
        idx = sys.argv.index("--debug-read-file")
        target = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        raise SystemExit(_debug_read_file(target))
    raise SystemExit(main())
