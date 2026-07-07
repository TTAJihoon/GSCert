"""시험 이력 '문서' 버튼: report\\<시험번호> 폴더의 파일들을 ZIP 으로 묶어 브라우저에 전달."""
import io
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET


def _report_base() -> str:
    return getattr(settings, "AGENT_REPORT_BASE_DIR", r"C:\Users\Administrator\report")


@require_GET
def download_report(request, test_no):
    """report\\<시험번호> 안의 모든 파일을 ZIP 으로 반환한다(첨부 다운로드)."""
    name = unicodedata.normalize("NFC", str(test_no or "")).strip()
    # 경로 조작 방지: 구분자/상위경로 금지
    if not name or "/" in name or "\\" in name or ".." in name:
        return JsonResponse({"error": "잘못된 시험번호입니다."}, status=400)

    folder = Path(_report_base()) / name
    if not folder.is_dir():
        return JsonResponse({"error": "다운로드할 문서 폴더가 없습니다."}, status=404)

    # `.scope` 는 다운로드 범위 캐시 마커라 ZIP 에 포함하지 않는다.
    files = [p for p in folder.rglob("*") if p.is_file() and p.name != ".scope"]
    if not files:
        return JsonResponse({"error": "폴더에 파일이 없습니다."}, status=404)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.relative_to(folder).as_posix())
    buffer.seek(0)

    zip_name = f"{name}.zip"
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = (
        f"attachment; filename=\"{zip_name}\"; filename*=UTF-8''{quote(zip_name)}"
    )
    response["Content-Length"] = str(buffer.getbuffer().nbytes)
    return response
