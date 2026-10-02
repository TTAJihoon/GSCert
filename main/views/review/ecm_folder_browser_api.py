"""산출물 폴더 탐색 API (ECM 점검 페이지·KOLAS 페이지 공용).

    GET  /api/projects/<번호>/browse/            ?ref=&center=&cert_date=   위치 하나의 항목 목록(JSON)
    GET  /api/projects/<번호>/browse/progress/   ?ref=                       zip 읽기 진행률(JSON)
    GET  /api/projects/<번호>/browse/download/   ?ref=                       파일 하나(또는 폴더 하나를 zip 으로)
    POST /api/projects/<번호>/browse/download/   ref 여러 개                 선택 항목을 하나의 zip 으로

다운로드는 숨은 iframe 으로 호출하므로, 오류도 JSON 이 아니라 `다운로드_오류.txt` 첨부로 돌려준다.
"""

import itertools
import logging
import mimetypes
import re
from urllib.parse import quote

from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from main.views.review.ecm_download_review_jobs import PROJECT_NUMBER_RE
from main.views.review.ecm_folder_browser import (
    BrowseError,
    describe_single_download,
    iter_selection_zip,
    list_location,
    zip_cache,
    zip_progress,
)
from main.views.review.kolas_api import _stream_body

logger = logging.getLogger(__name__)


def _json(payload, status=200):
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _check_project(project_number):
    if not PROJECT_NUMBER_RE.match(str(project_number or "")):
        raise BrowseError("프로젝트번호 형식이 올바르지 않습니다.", 400)
    return project_number


@require_GET
def browse(request, project_number):
    try:
        _check_project(project_number)
        payload = list_location(
            project_number,
            request.GET.get("ref") or None,
            center_hint=str(request.GET.get("center") or "").strip().lower(),
            cert_date=str(request.GET.get("cert_date") or "").strip(),
            sid=_clean_sid(request.GET.get("sid")),
        )
    except BrowseError as exc:
        return _json({"success": False, "message": exc.message}, exc.status)
    except Exception:
        logger.exception("folder browse failed: %s", project_number)
        return _json({"success": False, "message": "폴더를 읽는 중 오류가 발생했습니다."}, 500)
    return _json({"success": True, **payload})


SID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _clean_sid(value):
    value = str(value or "")
    return value if SID_RE.match(value) else ""


@require_POST
def browse_watch(request, project_number):
    """팝업이 열려 있다는 신호(action=beat, 약 3초마다)와 닫혔다는 신호(action=close, 즉시).

    보는 팝업이 모두 닫힌 미완성 zip 은 서버가 받기를 중단해 다음 zip 에 자리를 넘긴다.
    """
    sid = _clean_sid(request.POST.get("sid"))
    action = request.POST.get("action")
    if not sid or action not in ("beat", "close"):
        return _json({"success": False, "message": "sid/action 이 올바르지 않습니다."}, 400)
    if action == "close":
        zip_cache.release(sid)
    else:
        zip_cache.watch(sid)
    return _json({"success": True})


@require_GET
def browse_progress(request, project_number):
    """zip 을 읽는 중인 작업의 진행 상황({state, written, total, percent}). 화면이 폴링해 진행률 막대를 그린다."""
    try:
        _check_project(project_number)
        ref = request.GET.get("ref")
        if not ref:
            raise BrowseError("ref 가 필요합니다.", 400)
        return _json({"success": True, **zip_progress(project_number, ref)})
    except BrowseError as exc:
        return _json({"success": False, "message": exc.message}, exc.status)
    except Exception:
        logger.exception("folder browse progress failed: %s", project_number)
        return _json({"success": False, "message": "진행 상황을 읽지 못했습니다."}, 500)


def _attachment_name(filename):
    safe = str(filename or "download").replace('"', "").replace("\\", "_").replace("/", "_")
    ascii_fallback = "".join(ch if ord(ch) < 128 else "_" for ch in safe) or "download"
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe)}"


def _error_attachment(message):
    response = StreamingHttpResponse(iter([("다운로드 오류\n" + str(message) + "\n").encode("utf-8-sig")]), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = _attachment_name("다운로드_오류.txt")
    response["Cache-Control"] = "no-store"
    return response


def _primed(generator):
    """첫 조각을 미리 받아 와서, 시작 단계의 오류(ECM 접속 실패, 잘못된 항목 등)를 정상 응답 전에 잡는다."""
    first = next(generator, None)
    if first is None:
        return iter(())
    return itertools.chain([first], generator)


@require_http_methods(["GET", "POST"])
def browse_download(request, project_number):
    try:
        _check_project(project_number)
        if request.method == "GET":
            ref = request.GET.get("ref")
            single = describe_single_download(project_number, ref) if ref else None
            if single is None:
                refs = [ref] if ref else []
            else:
                filename, chunks = single
                return _file_response(request, filename, chunks)
        else:
            refs = request.POST.getlist("ref")
            if len(refs) == 1:
                single = describe_single_download(project_number, refs[0])
                if single is not None:
                    filename, chunks = single
                    return _file_response(request, filename, chunks)

        stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
        stream = _primed(iter_selection_zip(project_number, refs))
        response = StreamingHttpResponse(_stream_body(request, stream), content_type="application/zip")
        response["Content-Disposition"] = _attachment_name(f"{project_number}_산출물_{stamp}.zip")
        response["Cache-Control"] = "no-store"
        response["X-Accel-Buffering"] = "no"
        return response
    except BrowseError as exc:
        return _error_attachment(exc.message)
    except Exception as exc:
        logger.exception("folder browse download failed: %s", project_number)
        return _error_attachment(f"다운로드 중 오류가 발생했습니다: {exc}")


def _file_response(request, filename, chunks):
    stream = _primed(iter(chunks))
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = StreamingHttpResponse(_stream_body(request, stream), content_type=content_type)
    response["Content-Disposition"] = _attachment_name(filename)
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"
    return response
