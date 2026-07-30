import logging
from pathlib import Path
from urllib.parse import quote
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from django.conf import settings
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from main.views.review.ecm_download_review_jobs import (
    DownloadReviewJobRequestError,
    DownloadReviewNotFoundError,
    attach_active_project_states,
    cancel_download_review_job,
    create_download_review_job,
    force_stop_download_review_jobs,
    get_active_job_payload,
    get_bulk_projects_zip_response,
    get_job_detail_payload,
    get_job_projects_payload,
    get_job_results_excel_response,
    get_jobs_payload,
    get_latest_project_results_payload,
    get_project_change_note_payload,
    get_project_results_excel_response,
    get_project_results_payload,
    get_rule_result_artifact_response,
    mark_rule_result_manual_pass,
    parse_json_body,
)
from main.views.review.ecm_reference_db import (
    ReferenceDbError,
    ReferenceDbMissing,
    ReferenceDbSchemaError,
    ReferenceQueryError,
    get_projects_by_numbers,
    list_projects,
)
from main.views.review.ecm_download_review_centers import (
    allowed_centers_for_host,
    center_choices,
    default_center_for_host,
    is_center_allowed_for_host,
    normalize_center_code,
)
from main.views.review.ecm_rulebase import (
    get_rulebase_bundle_payload,
    get_rulebase_manifest_payload,
)
from main.views.review.ecm_pl_assignment import (
    PlAssignmentError,
    apply_pl_assignment_changes,
    get_pl_assignment_payload,
)

logger = logging.getLogger(__name__)


@require_GET
def projects(request):
    try:
        query_params = _query_params_with_host_default_center(request)
        _ensure_request_center_allowed(request, query_params.get("center"))
        payload = list_projects(query_params)
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
        payload = _error_payload(exc, "기준 DB 조회 중 오류가 발생했습니다.")
        status = 500

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def local_review_health(request):
    denied = _local_review_auth_denied(request)
    if denied:
        return denied
    payload = {
        "success": True,
        "ok": True,
        "server_time": timezone.now().isoformat(),
    }
    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def local_review_project_metadata(request, project_number):
    denied = _local_review_auth_denied(request)
    if denied:
        return denied
    requested_center = request.GET.get("center")
    try:
        if requested_center:
            # 명시된 센터로만 조회
            centers_to_search = [_ensure_request_center_allowed(request, requested_center)]
        else:
            # 센터 미지정(로컬 앱) → 모든 센터에서 프로젝트번호로 조회한다.
            # reference_project(공유 PostgreSQL)에는 전 센터 데이터가 있고 프로젝트번호는
            # 센터 간 고유하므로, 호스트 허용 센터로 제한하지 않고 전 센터를 검색해야
            # 다른 센터(예: 상암/영남) 프로젝트도 로컬 앱에서 조회된다. 첫 매치를 사용.
            centers_to_search = [choice["code"] for choice in center_choices()]
        project = None
        for center_code in centers_to_search:
            projects_payload = get_projects_by_numbers([project_number], center_code=center_code)
            if projects_payload and projects_payload[0]:
                project = projects_payload[0]
                break
        if not project:
            payload = _error_payload(
                ReferenceQueryError("Project metadata was not found."),
                "Project metadata was not found.",
            )
            status = 404
        else:
            payload = {
                "success": True,
                "project": {
                    "center_code": project.get("center_code", ""),
                    "center_label": project.get("center_label", ""),
                    "project_number": project.get("project_number", ""),
                    "company_name": project.get("company", ""),
                    "product_name": project.get("product", ""),
                    "pl_name": project.get("pl", ""),
                    "wd_name": project.get("wd", ""),
                    "request_date": project.get("request_date", ""),
                    "contract_date": project.get("contract_date", ""),
                    "cert_date": project.get("cert_date", ""),
                    "inspection_date": project.get("inspection_date", ""),
                    "review": project.get("review", ""),
                    "review_raw": project.get("review_raw", ""),
                    "start_date": project.get("start_date", ""),
                    "end_date": project.get("end_date", ""),
                },
            }
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
        payload = _error_payload(exc, "Reference DB lookup failed.")
        status = 500

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def local_review_rules_manifest(request):
    denied = _local_review_auth_denied(request)
    if denied:
        return denied
    payload = get_rulebase_manifest_payload()
    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def local_review_rules_bundle(request):
    denied = _local_review_auth_denied(request)
    if denied:
        return denied
    payload, status = get_rulebase_bundle_payload(request.GET.get("version"))
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def local_review_app_download(request):
    package_dir = _local_review_package_dir()
    exe_path = package_dir / _local_review_exe_name()
    if not package_dir.is_dir() or not exe_path.is_file():
        raise Http404("로컬 점검 프로그램 패키지가 준비되지 않았습니다.")

    response = StreamingHttpResponse(
        _iter_local_review_app_zip(package_dir),
        content_type="application/zip",
    )
    response["Content-Disposition"] = f'attachment; filename="{_local_review_archive_name()}"'
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"
    return response


@require_http_methods(["GET", "POST"])
def jobs(request):
    if request.method == "GET":
        return _jobs_list(request)
    return _jobs_create(request)


def _jobs_list(request):
    try:
        query_params = request.GET.copy()
        if query_params.get("center"):
            query_params["center"] = _ensure_request_center_allowed(request, query_params.get("center"))
        payload = get_jobs_payload(query_params)
        status = 200
    except ReferenceQueryError as exc:
        payload = _error_payload(exc, str(exc))
        status = 400
    except DownloadReviewJobRequestError as exc:
        payload = _error_payload(exc, str(exc), details=exc.details)
        status = exc.status_code

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _jobs_create(request):
    try:
        payload = parse_json_body(request)
        if not payload.get("center"):
            payload["center"] = default_center_for_host(request.get_host())
        _ensure_request_center_allowed(request, payload.get("center"))
        response_payload = create_download_review_job(
            payload,
            request_ip=_client_ip(request),
        )
        status = 201
    except ReferenceQueryError as exc:
        response_payload = _error_payload(exc, str(exc))
        status = 400
    except DownloadReviewJobRequestError as exc:
        response_payload = _error_payload(exc, str(exc), details=exc.details)
        status = exc.status_code
    except ReferenceDbMissing as exc:
        response_payload = _error_payload(exc, str(exc))
        status = 503
    except ReferenceDbSchemaError as exc:
        response_payload = _error_payload(exc, str(exc))
        status = 500
    except ReferenceDbError as exc:
        response_payload = _error_payload(exc, "기준 DB 조회 중 오류가 발생했습니다.")
        status = 500

    response = JsonResponse(response_payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def active_job(request):
    response = JsonResponse(get_active_job_payload(), json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def job_detail(request, job_id):
    return _json_or_not_found(lambda: get_job_detail_payload(job_id))


@require_GET
def job_projects(request, job_id):
    return _json_or_not_found(lambda: get_job_projects_payload(job_id))


@require_POST
def job_cancel(request, job_id):
    try:
        payload = cancel_download_review_job(job_id)
        status = 200
    except DownloadReviewNotFoundError as exc:
        payload = _error_payload(exc, str(exc))
        status = exc.status_code
    except DownloadReviewJobRequestError as exc:
        payload = _error_payload(exc, str(exc), details=exc.details)
        status = exc.status_code

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def jobs_force_stop(request):
    """진행중(RUNNING 포함) 작업을 강제 종료하고 워커 락을 해제한다.

    워커 비정상 종료로 작업이 멈춘 채 새 작업을 시작할 수 없을 때 사용한다.
    body 에 job_id 가 있으면 해당 작업만, 없으면 활성 작업 전체를 종료한다.
    """
    job_id = None
    try:
        body = parse_json_body(request)
    except DownloadReviewJobRequestError:
        body = {}
    if isinstance(body, dict):
        job_id = body.get("job_id") or None

    try:
        payload = force_stop_download_review_jobs(job_id)
        status = 200
    except DownloadReviewNotFoundError as exc:
        payload = _error_payload(exc, str(exc))
        status = exc.status_code

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def job_project_results(request, job_project_id):
    return _json_or_not_found(lambda: get_project_results_payload(job_project_id))


@require_GET
def job_project_change_note(request, job_project_id):
    return _json_or_not_found(lambda: get_project_change_note_payload(job_project_id))


@require_GET
def job_project_results_excel(request, job_project_id):
    return _file_or_not_found(lambda: get_project_results_excel_response(job_project_id))


@require_GET
def job_results_excel(request, job_id):
    return _file_or_not_found(lambda: get_job_results_excel_response(job_id))


@require_GET
def latest_project_results(request, project_number):
    center_code = request.GET.get("center") or default_center_for_host(request.get_host())
    try:
        _ensure_request_center_allowed(request, center_code)
    except ReferenceQueryError as exc:
        response = JsonResponse(_error_payload(exc, str(exc)), status=400, json_dumps_params={"ensure_ascii": False})
        response["Cache-Control"] = "no-store"
        return response
    return _json_or_not_found(lambda: get_latest_project_results_payload(project_number, center_code))


@require_GET
def bulk_download_projects_zip(request):
    project_numbers = request.GET.getlist("pn")
    center_code = request.GET.get("center") or default_center_for_host(request.get_host())
    try:
        _ensure_request_center_allowed(request, center_code)
        return get_bulk_projects_zip_response(project_numbers, center_code=center_code)
    except ReferenceQueryError as exc:
        response = JsonResponse(
            _error_payload(exc, str(exc)),
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )
        response["Cache-Control"] = "no-store"
        return response
    except DownloadReviewJobRequestError as exc:
        response = JsonResponse(
            {"success": False, "message": str(exc)},
            status=exc.status_code,
            json_dumps_params={"ensure_ascii": False},
        )
        response["Cache-Control"] = "no-store"
        return response


@require_http_methods(["GET", "POST"])
def project_full_documents_download(request, project_number):
    if request.method == "GET":
        cert_date = str(request.GET.get("cert_date") or "").strip()
        try:
            from main.views.testing.history_download import iter_full_project_documents_zip

            response = StreamingHttpResponse(
                iter_full_project_documents_zip(project_number, cert_date),
                content_type="application/zip",
            )
            safe_name = str(project_number).replace('"', "").replace("\\", "_").replace("/", "_")
            response["Content-Disposition"] = f'attachment; filename="{safe_name}.zip"'
            response["Cache-Control"] = "no-store"
            response["X-Accel-Buffering"] = "no"
            return response
        except Exception as exc:
            logger.exception("download-review full project document stream failed: %s", project_number)
            response = JsonResponse(
                _error_payload(
                    exc,
                    f"{project_number} ECM 전체 폴더 다운로드를 실패하였습니다. 다시 요청해주세요.",
                ),
                status=500,
                json_dumps_params={"ensure_ascii": False},
            )
            response["Cache-Control"] = "no-store"
            return response

    try:
        body = parse_json_body(request)
    except DownloadReviewJobRequestError as exc:
        response = JsonResponse(
            _error_payload(exc, str(exc), details=exc.details),
            status=exc.status_code,
            json_dumps_params={"ensure_ascii": False},
        )
        response["Cache-Control"] = "no-store"
        return response

    cert_date = str(body.get("cert_date") or "").strip()
    try:
        from main.views.testing.history_download import download_full_project_documents

        result = download_full_project_documents(project_number, cert_date)
    except Exception as exc:
        logger.exception("download-review full project document download failed: %s", project_number)
        response = JsonResponse(
            _error_payload(
                exc,
                f"{project_number} ECM 전체 폴더 다운로드를 실패하였습니다. 다시 요청해주세요.",
            ),
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )
        response["Cache-Control"] = "no-store"
        return response

    response = JsonResponse(
        {
            "success": True,
            "download_url": f"/history/report/{quote(str(project_number))}/download/",
            "doc_count": result.get("doc_count", 0),
            "center": result.get("center", ""),
        },
        json_dumps_params={"ensure_ascii": False},
    )
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def rule_result_artifact(request, result_id, artifact_id):
    try:
        return get_rule_result_artifact_response(result_id, artifact_id)
    except DownloadReviewNotFoundError as exc:
        response = JsonResponse(_error_payload(exc, str(exc)), status=exc.status_code, json_dumps_params={"ensure_ascii": False})
        response["Cache-Control"] = "no-store"
        return response


@require_POST
def rule_result_manual_pass(request, result_id):
    try:
        payload = parse_json_body(request)
        response_payload = mark_rule_result_manual_pass(
            result_id,
            payload.get("memo"),
            requested_by=_client_ip(request),
        )
        status = 200
    except DownloadReviewJobRequestError as exc:
        response_payload = _error_payload(exc, str(exc), details=exc.details)
        status = exc.status_code
    except DownloadReviewNotFoundError as exc:
        response_payload = _error_payload(exc, str(exc))
        status = exc.status_code
    except Exception as exc:
        logger.exception("Manual pass override failed: %s", result_id)
        response_payload = _error_payload(
            exc,
            "수동 적합 처리 중 서버 오류가 발생했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.",
        )
        status = 500

    response = JsonResponse(response_payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def pl_assignments(request):
    payload = get_pl_assignment_payload()
    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def pl_assignments_apply(request):
    try:
        payload = parse_json_body(request)
        response_payload = apply_pl_assignment_changes(payload.get("changes"))
        status = 200
    except (PlAssignmentError, DownloadReviewJobRequestError) as exc:
        response_payload = _error_payload(exc, str(exc), details=getattr(exc, "details", None))
        status = getattr(exc, "status_code", 400)

    response = JsonResponse(response_payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _error_payload(exc, message, details=None):
    payload = {
        "success": False,
        "error_code": getattr(exc, "error_code", "error"),
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def _json_or_not_found(factory):
    try:
        payload = factory()
        status = 200
    except DownloadReviewJobRequestError as exc:
        payload = _error_payload(exc, str(exc), details=exc.details)
        status = exc.status_code
    except DownloadReviewNotFoundError as exc:
        payload = _error_payload(exc, str(exc))
        status = exc.status_code

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _file_or_not_found(factory):
    try:
        return factory()
    except DownloadReviewJobRequestError as exc:
        response = JsonResponse(_error_payload(exc, str(exc), details=exc.details), status=exc.status_code, json_dumps_params={"ensure_ascii": False})
        response["Cache-Control"] = "no-store"
        return response
    except DownloadReviewNotFoundError as exc:
        response = JsonResponse(_error_payload(exc, str(exc)), status=exc.status_code, json_dumps_params={"ensure_ascii": False})
        response["Cache-Control"] = "no-store"
        return response


def _query_params_with_host_default_center(request):
    query_params = request.GET.copy()
    if not query_params.get("center"):
        query_params["center"] = default_center_for_host(request.get_host())
    return query_params


def _local_review_auth_denied(request):
    """local-review API 토큰 검증. settings.LOCAL_REVIEW_API_TOKEN 이 설정된 경우에만
    헤더 X-Local-Review-Token 일치를 요구한다. 미설정이면 None(=통과, 기존 동작)."""
    token = getattr(settings, "LOCAL_REVIEW_API_TOKEN", "") or ""
    if not token:
        return None
    provided = request.headers.get("X-Local-Review-Token", "")
    if provided and provided == token:
        return None
    response = JsonResponse(
        {"success": False, "error_code": "unauthorized", "message": "유효한 인증 토큰이 필요합니다."},
        status=401,
    )
    response["Cache-Control"] = "no-store"
    return response


def _local_review_package_dir():
    configured = getattr(settings, "LOCAL_REVIEW_APP_PACKAGE_DIR", None)
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(r"C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard").resolve()


def _local_review_exe_name():
    return str(getattr(settings, "LOCAL_REVIEW_APP_EXE_NAME", "GSCertLocalReviewDashboard.exe") or "GSCertLocalReviewDashboard.exe")


def _local_review_archive_name():
    return str(getattr(settings, "LOCAL_REVIEW_APP_ARCHIVE_NAME", "GSCertLocalReviewDashboard.zip") or "GSCertLocalReviewDashboard.zip")


class _ZipStreamBuffer:
    def __init__(self):
        self._chunks = []

    def write(self, data):
        if data:
            self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        return None

    def drain(self):
        chunks = self._chunks
        self._chunks = []
        return chunks


def _iter_local_review_app_zip(package_dir):
    buffer = _ZipStreamBuffer()
    package_parent = package_dir.parent
    files = sorted(path for path in package_dir.rglob("*") if path.is_file())

    with ZipFile(buffer, mode="w", compression=ZIP_STORED) as zip_file:
        for file_path in files:
            archive_name = file_path.relative_to(package_parent).as_posix()
            zip_info = ZipInfo.from_file(file_path, archive_name)
            zip_info.compress_type = ZIP_STORED

            with zip_file.open(zip_info, mode="w") as target:
                yield from buffer.drain()
                with file_path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
                        yield from buffer.drain()
            yield from buffer.drain()

    yield from buffer.drain()


def _ensure_request_center_allowed(request, center_code):
    try:
        normalized = normalize_center_code(center_code)
    except ValueError as exc:
        raise ReferenceQueryError(str(exc)) from exc
    if not is_center_allowed_for_host(normalized, request.get_host()):
        raise ReferenceQueryError("이 서버에서 처리하지 않는 센터입니다.")
    return normalized


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
