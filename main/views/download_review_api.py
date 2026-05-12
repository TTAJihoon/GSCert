from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from main.services.download_review_jobs import (
    DownloadReviewJobRequestError,
    DownloadReviewNotFoundError,
    create_download_review_job,
    get_active_job_payload,
    get_job_detail_payload,
    get_job_projects_payload,
    get_jobs_payload,
    get_project_results_payload,
    parse_json_body,
)
from main.services.reference_db import (
    ReferenceDbError,
    ReferenceDbMissing,
    ReferenceDbSchemaError,
    ReferenceQueryError,
    list_projects,
)


@require_GET
def projects(request):
    try:
        payload = list_projects(request.GET)
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


@require_http_methods(["GET", "POST"])
def jobs(request):
    if request.method == "GET":
        return _jobs_list(request)
    return _jobs_create(request)


def _jobs_list(request):
    try:
        payload = get_jobs_payload(request.GET)
        status = 200
    except DownloadReviewJobRequestError as exc:
        payload = _error_payload(exc, str(exc), details=exc.details)
        status = exc.status_code

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _jobs_create(request):
    try:
        payload = parse_json_body(request)
        response_payload = create_download_review_job(
            payload,
            request_ip=_client_ip(request),
        )
        status = 201
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


@require_GET
def job_project_results(request, job_project_id):
    return _json_or_not_found(lambda: get_project_results_payload(job_project_id))


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
    except DownloadReviewNotFoundError as exc:
        payload = _error_payload(exc, str(exc))
        status = exc.status_code

    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
