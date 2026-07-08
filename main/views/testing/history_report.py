"""시험 이력 다운로드 서빙.

- 전체(#2): report\\<시험번호> 폴더의 모든 파일을 ZIP 으로 **스트리밍** 전달(download_report).
  스트리밍이라 첫 파일부터 즉시 전송돼 큰 프로젝트에서도 다운로드가 바로 시작된다.
- 성적서(#1): report\\__report\\<시험번호> 의 시험성적서 파일을 **그대로** 전달
  (1개면 원본 파일, 여러 개면 ZIP). (download_report_document)

주의(파일명 인코딩): Content-Disposition 헤더 값에 비ASCII(한글)를 직접 넣으면 Django 가
헤더 전체를 RFC2047(`=?utf-8?b?..?=`)로 인코딩해 브라우저가 파일명을 못 읽는다. 따라서
filename= 은 ASCII 폴백만, 실제 이름은 filename*=UTF-8''<percent-encoded> 로만 넣는다.
"""
import mimetypes
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import quote

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_GET

from main.views.testing.history_download import all_dir, doc_dir


def _safe_name(test_no):
    name = unicodedata.normalize("NFC", str(test_no or "")).strip()
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("__"):
        return None
    return name


def _content_disposition(name: str) -> str:
    """ASCII 폴백 + filename*(UTF-8) 로 헤더를 ASCII 로만 구성한다."""
    ascii_fallback = (name.encode("ascii", "ignore").decode("ascii") or "download").replace('"', "")
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_fallback, quote(name))


class _ChunkBuffer:
    """zipfile 이 write 한 바이트를 청크로 흘려보내기 위한 파일류 객체."""

    def __init__(self):
        self._chunks = []

    def write(self, data):
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        return None

    def take(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks = []
        return data


def _iter_zip(files, folder):
    """폴더의 파일들을 ZIP 으로 압축하며 파일 단위로 바이트를 yield(스트리밍)."""
    buffer = _ChunkBuffer()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.relative_to(folder).as_posix())
            chunk = buffer.take()
            if chunk:
                yield chunk
    tail = buffer.take()
    if tail:
        yield tail


def _zip_stream_response(folder: Path, zip_name: str) -> StreamingHttpResponse:
    files = [p for p in folder.rglob("*") if p.is_file()]
    if not files:
        return JsonResponse({"error": "폴더에 파일이 없습니다."}, status=404)
    response = StreamingHttpResponse(_iter_zip(files, folder), content_type="application/zip")
    response["Content-Disposition"] = _content_disposition(zip_name)
    return response


def _file_response(path: Path) -> HttpResponse:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = path.read_bytes()
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = _content_disposition(path.name)
    response["Content-Length"] = str(len(data))
    return response


@require_GET
def download_report(request, test_no):
    """전체(#2): report\\<시험번호> 안의 모든 파일을 ZIP 으로 스트리밍 반환한다."""
    name = _safe_name(test_no)
    if not name:
        return JsonResponse({"error": "잘못된 시험번호입니다."}, status=400)
    folder = all_dir(name)
    if not folder.is_dir():
        return JsonResponse({"error": "다운로드할 문서 폴더가 없습니다."}, status=404)
    return _zip_stream_response(folder, f"{name}.zip")


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
    return _zip_stream_response(folder, f"{name}_시험성적서.zip")
