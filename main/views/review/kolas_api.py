"""KOLAS 점검 페이지(/kolas/) 전용 API.

프로젝트 목록(KolasProject) / PL 배정 / 시험성적서 zip 다운로드만 따로 두고, 점검 작업
생성·진행·결과 조회는 기존 ECM 점검 API(/api/jobs/ 등)를 그대로 쓴다
(작업 생성 시 source="kolas" 로 구분).
"""

import logging
from urllib.parse import quote

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from main.models import KolasProject
from main.views.review.ecm_download_review_api import (
    _client_ip,
    _ensure_request_center_allowed,
    _error_payload,
    _query_params_with_host_default_center,
)
from main.views.review.ecm_download_review_jobs import (
    PROJECT_NUMBER_RE,
    DownloadReviewJobRequestError,
    attach_active_project_states,
    parse_json_body,
)
from main.views.review.ecm_pl_assignment import (
    PlAssignmentError,
    apply_pl_assignment_changes,
    get_pl_assignment_payload,
)
from main.views.review.ecm_reference_db import (
    UNASSIGNED_CENTER_CODE,
    ReferenceDbError,
    ReferenceDbMissing,
    ReferenceDbSchemaError,
    ReferenceQueryError,
    list_kolas_projects,
)
from main.views.review.kolas_report_download import iter_report_zip
from main.views.review.kolas_report_task import (
    ReportTaskReporter,
    list_tasks,
    parse_task_id,
    tracked_stream,
)
from main.views.testing.history_download import _single_error_zip

logger = logging.getLogger(__name__)

DEFAULT_REPORT_MAX_PROJECTS = 500


def _json(payload, status=200):
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def kolas_projects(request):
    try:
        query_params = _query_params_with_host_default_center(request)
        center = str(query_params.get("center") or "").strip().lower()
        if center != UNASSIGNED_CENTER_CODE:
            _ensure_request_center_allowed(request, center)
        payload = list_kolas_projects(query_params)
        payload = attach_active_project_states(payload)
        status = 200
    except ReferenceQueryError as exc:
        payload = _error_payload(exc, str(exc))
        status = 400
    except ReferenceDbMissing as exc:
        payload = _error_payload(exc, str(exc))
        status = 503
    except ReferenceDbSchemaError as exc:
        payload = _error_payload(exc, str(exc))
        status = 500
    except ReferenceDbError as exc:
        payload = _error_payload(exc, "KOLAS 프로젝트 목록 조회 중 오류가 발생했습니다.")
        status = 500
    return _json(payload, status)


@require_GET
def kolas_pl_assignments(request):
    return _json(get_pl_assignment_payload(kolas=True))


@require_POST
def kolas_pl_assignments_apply(request):
    try:
        payload = parse_json_body(request)
        response_payload = apply_pl_assignment_changes(payload.get("changes"), kolas=True)
        status = 200
    except (PlAssignmentError, DownloadReviewJobRequestError) as exc:
        response_payload = _error_payload(exc, str(exc), details=getattr(exc, "details", None))
        status = getattr(exc, "status_code", 400)
    return _json(response_payload, status)


@require_POST
def kolas_report_download(request):
    """선택한 프로젝트의 시험성적서(Word/PDF)를 ECM 에서 받아 word/, pdf/ 폴더로 나눈 zip 으로 전달.

    form POST(pn 여러 개)를 받아 StreamingHttpResponse 로 흘려보낸다. 브라우저 이동 없이
    숨은 iframe 으로 호출하므로, 오류도 JSON 이 아니라 '다운로드 오류.txt' 가 든 zip 으로 돌려준다.
    """
    max_projects = getattr(settings, "KOLAS_REPORT_MAX_PROJECTS", DEFAULT_REPORT_MAX_PROJECTS)
    numbers = []
    for raw in request.POST.getlist("pn"):
        value = str(raw or "").strip()
        if PROJECT_NUMBER_RE.match(value) and value not in numbers:
            numbers.append(value)

    # refresh=1: 서버 저장본을 무시하고 ECM 최신본으로 다시 받아 저장본을 교체한다(화면 버튼은 없음).
    refresh = str(request.POST.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
    if not numbers:
        return _error_zip("선택된 프로젝트가 없거나 프로젝트번호 형식이 올바르지 않습니다.")
    if len(numbers) > max_projects:
        return _error_zip(f"한 번에 최대 {max_projects}개 프로젝트까지 다운로드할 수 있습니다. (선택 {len(numbers)}개)")

    rows = {
        row.project_number: row
        for row in KolasProject.objects.using(getattr(settings, "REFERENCE_DATABASE_ALIAS", "reference"))
        .filter(project_number__in=numbers)
    }
    projects = []
    missing = []
    for number in numbers:
        row = rows.get(number)
        if row is None:
            missing.append(number)
            continue
        projects.append({
            "project_number": row.project_number,
            "center_code": row.center_code,
            "cert_date_full": row.cert_committee_date.isoformat() if row.cert_committee_date else "",
        })

    # 진행 상황 기록: 화면이 보낸 task_id 로 작업 행을 만들고, zip 이 흘러가는 동안 프로젝트 단위로 갱신한다.
    reporter = ReportTaskReporter.start(
        parse_task_id(request.POST.get("task_id")), len(projects) + len(missing), requested_ip=_client_ip(request),
    )
    stream = tracked_stream(
        iter_report_zip(projects, missing_numbers=missing, refresh=refresh, reporter=reporter), reporter,
    )

    stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
    filename = f"KOLAS_시험성적서_{stamp}.zip"
    response = StreamingHttpResponse(
        _stream_body(request, stream),
        content_type="application/zip",
    )
    response["Content-Disposition"] = (
        f"attachment; filename=\"kolas_reports_{stamp}.zip\"; filename*=UTF-8''{quote(filename)}"
    )
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"
    return response


def _stream_body(request, chunks):
    """zip 조각 생성기를 응답 본문으로 만든다.

    운영 서버는 ASGI(Daphne)다. ASGI 에서 StreamingHttpResponse 에 '동기' 생성기를 주면 Django 가
    생성기를 끝까지 소비해 list 로 모은 뒤에야 첫 바이트를 보낸다(=서버 메모리에 zip 전체를 쌓고
    ECM 다운로드가 모두 끝나야 브라우저 다운로드가 시작됨). 그래서 ASGI 요청이면 비동기 생성기로
    감싸 조각마다 즉시 전송하고, 블로킹 HTTP(ECM)는 스레드에서 실행한다. WSGI 에서는 동기 생성기가
    그대로 점진 전송된다.
    """
    if hasattr(request, "scope"):
        return _async_chunks(chunks)
    return chunks


def _next_chunk(iterator, done):
    """스레드 풀에서 다음 조각을 만든다. 진행률 기록으로 이 스레드에 열린 DB 연결은 매번 닫아 연결이 쌓이지 않게 한다."""
    try:
        return next(iterator, done)
    finally:
        connections.close_all()


async def _async_chunks(chunks):
    iterator = iter(chunks)
    done = object()
    try:
        while True:
            chunk = await sync_to_async(_next_chunk, thread_sensitive=False)(iterator, done)
            if chunk is done:
                break
            yield chunk
    finally:
        # 브라우저가 중간에 취소해도 ECM 세션/생성기를 정리한다.
        close = getattr(iterator, "close", None)
        if close is not None:
            await sync_to_async(close, thread_sensitive=False)()


@require_GET
def kolas_report_tasks(request):
    """결과서 다운로드 진행 상황 목록(최근 순). 화면의 '현재 작업 진행 상황'·'작업 조회' 탭이 폴링한다."""
    try:
        limit = int(request.GET.get("limit") or 20)
    except ValueError:
        limit = 20
    return _json({"success": True, "items": list_tasks(limit)})


def _error_zip(message):
    response = StreamingHttpResponse(_single_error_zip(message), content_type="application/zip")
    response["Content-Disposition"] = (
        "attachment; filename=\"kolas_reports_error.zip\"; "
        f"filename*=UTF-8''{quote('KOLAS_시험성적서_오류.zip')}"
    )
    response["Cache-Control"] = "no-store"
    return response
