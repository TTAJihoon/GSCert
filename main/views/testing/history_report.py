"""시험 이력 다운로드 서빙.

- 전체(#2): 미리 만들어 둔 report\\__zip\\<시험번호>.zip 을 스트리밍(FileResponse 대체:
  StreamingHttpResponse) 하고, **전송이 끝나면 원본 폴더와 zip 을 삭제**한다.
- 성적서(#1): report\\__report\\<시험번호> 의 파일을 그대로(1개면 원본, 여러 개면 zip)
  메모리로 읽어 전달하고 **폴더를 즉시 삭제**한다.

파일명 인코딩: Content-Disposition 에 비ASCII(한글)를 직접 넣으면 Django 가 헤더 전체를
RFC2047 로 인코딩해 브라우저가 못 읽는다. filename= 은 ASCII 폴백만, 실제 이름은
filename*=UTF-8''<percent-encoded> 로만 넣는다.
"""
import io
import mimetypes
import shutil
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import quote

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET

from main.views.testing.history_download import all_dir, doc_dir, zip_path

_CHUNK = 64 * 1024


def _safe_name(test_no):
    name = unicodedata.normalize("NFC", str(test_no or "")).strip()
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("__"):
        return None
    return name


def _content_disposition(name: str) -> str:
    ascii_fallback = (name.encode("ascii", "ignore").decode("ascii") or "download").replace('"', "")
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_fallback, quote(name))


def _cleanup(paths):
    """전송 완료(또는 중단) 후 서버 디스크의 원본 폴더/zip 을 삭제한다."""
    for p in paths:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except OSError:
            pass


def _zip_bytes(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(folder).as_posix())
    return buf.getvalue()


def _iter_file_then_cleanup(file_path: Path, cleanup_paths):
    """파일을 청크로 스트리밍하고, 다 보낸 뒤(또는 중단 시) cleanup_paths 를 삭제."""
    try:
        with open(file_path, "rb") as fp:
            while True:
                chunk = fp.read(_CHUNK)
                if not chunk:
                    break
                yield chunk
    finally:
        _cleanup(cleanup_paths)


def _attachment(response, name):
    response["Content-Disposition"] = _content_disposition(name)
    return response


@require_GET
def download_report(request, test_no):
    """전체(#2): 미리 만든 ZIP 을 스트리밍하고 전송 후 원본 폴더+ZIP 을 삭제한다."""
    name = _safe_name(test_no)
    if not name:
        return JsonResponse({"error": "잘못된 시험번호입니다."}, status=400)

    folder = all_dir(name)
    zp = zip_path(name)

    if zp.is_file():
        size = zp.stat().st_size
        response = StreamingHttpResponse(
            _iter_file_then_cleanup(zp, [zp, folder]),
            content_type="application/zip",
        )
        response["Content-Length"] = str(size)
        return _attachment(response, f"{name}.zip")

    # 폴백: 미리 만든 ZIP 이 없으면 폴더에서 즉석 압축(메모리) 후 폴더 삭제.
    if not folder.is_dir():
        return JsonResponse({"error": "다운로드할 문서 폴더가 없습니다."}, status=404)
    data = _zip_bytes(folder)
    if not data or len(zipfile.ZipFile(io.BytesIO(data)).namelist()) == 0:
        return JsonResponse({"error": "폴더에 파일이 없습니다."}, status=404)
    _cleanup([folder, zp])
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Length"] = str(len(data))
    return _attachment(response, f"{name}.zip")


@require_GET
def download_report_document(request, test_no):
    """성적서(#1): 파일을 메모리로 읽어 전달하고 폴더를 즉시 삭제한다.

    파일이 1개면 원본 파일 그대로, 여러 개면 ZIP.
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
        path = files[0]
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        file_name = path.name
        _cleanup([folder])
        response = HttpResponse(data, content_type=content_type)
        response["Content-Length"] = str(len(data))
        return _attachment(response, file_name)

    data = _zip_bytes(folder)
    _cleanup([folder])
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Length"] = str(len(data))
    return _attachment(response, f"{name}_시험성적서.zip")
