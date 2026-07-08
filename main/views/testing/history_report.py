"""시험 이력 다운로드 서빙.

- 전체(#2): report\\<시험번호> 폴더의 모든 파일을 ZIP 으로 묶어 전달(download_report).
- 성적서(#1): report\\__report\\<시험번호> 의 시험성적서 파일을 **그대로** 전달
  (1개면 원본 파일, 여러 개면 ZIP). (download_report_document)
"""
import io
import mimetypes
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import quote

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from main.views.testing.history_download import all_dir, doc_dir


def _safe_name(test_no):
    name = unicodedata.normalize("NFC", str(test_no or "")).strip()
    # 경로 조작 방지 + 내부 전용 폴더명 차단
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("__"):
        return None
    return name


def _zip_response(folder: Path, zip_name: str) -> HttpResponse:
    files = [p for p in folder.rglob("*") if p.is_file()]
    if not files:
        return JsonResponse({"error": "폴더에 파일이 없습니다."}, status=404)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.relative_to(folder).as_posix())
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = (
        f"attachment; filename=\"{zip_name}\"; filename*=UTF-8''{quote(zip_name)}"
    )
    response["Content-Length"] = str(buffer.getbuffer().nbytes)
    return response


def _file_response(path: Path) -> HttpResponse:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = path.read_bytes()
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = (
        f"attachment; filename=\"{path.name}\"; filename*=UTF-8''{quote(path.name)}"
    )
    response["Content-Length"] = str(len(data))
    return response


@require_GET
def download_report(request, test_no):
    """전체(#2): report\\<시험번호> 안의 모든 파일을 ZIP 으로 반환한다."""
    name = _safe_name(test_no)
    if not name:
        return JsonResponse({"error": "잘못된 시험번호입니다."}, status=400)
    folder = all_dir(name)
    if not folder.is_dir():
        return JsonResponse({"error": "다운로드할 문서 폴더가 없습니다."}, status=404)
    return _zip_response(folder, f"{name}.zip")


@require_GET
def download_report_document(request, test_no):
    """성적서(#1): report\\__report\\<시험번호> 의 성적서를 그대로 반환한다.

    파일이 1개면 원본 파일 그대로(ZIP 아님), 여러 개면 ZIP.
    """
    name = _safe_name(test_no)
    if not name:
        return JsonResponse({"error": "잘못된 시험번호입니다."}, status=400)
    folder = doc_dir(name)
    if not folder.is_dir():
        return JsonResponse({"error": "다운로드할 성적서가 없습니다."}, status=404)
    files = [p for p in folder.rglob("*") if p.is_file()]
    if not files:
        return JsonResponse({"error": "성적서 파일이 없습니다."}, status=404)
    if len(files) == 1:
        return _file_response(files[0])
    return _zip_response(folder, f"{name}_시험성적서.zip")
