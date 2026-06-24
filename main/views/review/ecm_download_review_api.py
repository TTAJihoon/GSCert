from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from main.views.review.ecm_download_review_jobs import (
    DownloadReviewJobRequestError,
    DownloadReviewNotFoundError,
    attach_active_project_states,
    cancel_download_review_job,
    create_download_review_job,
    get_active_job_payload,
    get_bulk_projects_zip_response,
    get_job_detail_payload,
    get_job_projects_payload,
    get_job_results_excel_response,
    get_jobs_payload,
    get_latest_project_results_payload,
    get_project_results_excel_response,
    get_project_results_payload,
    get_rule_result_artifact_response,
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
from main.views.review.ecm_rulebase import (
    get_rulebase_bundle_payload,
    get_rulebase_manifest_payload,
)


@require_GET
def projects(request):
    try:
        payload = list_projects(request.GET)
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
    center_code = request.GET.get("center")
    try:
        projects_payload = get_projects_by_numbers([project_number], center_code=center_code)
        project = projects_payload[0] if projects_payload else None
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
                    "start_date": "",
                    "end_date": "",
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
    payload = get_rulebase_manifest_payload()
    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def local_review_rules_bundle(request):
    payload, status = get_rulebase_bundle_payload(request.GET.get("version"))
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


@require_GET
def job_project_results(request, job_project_id):
    return _json_or_not_found(lambda: get_project_results_payload(job_project_id))


@require_GET
def job_project_results_excel(request, job_project_id):
    return _file_or_not_found(lambda: get_project_results_excel_response(job_project_id))


@require_GET
def job_results_excel(request, job_id):
    return _file_or_not_found(lambda: get_job_results_excel_response(job_id))


@require_GET
def latest_project_results(request, project_number):
    return _json_or_not_found(lambda: get_latest_project_results_payload(project_number, request.GET.get("center")))


@require_GET
def bulk_download_projects_zip(request):
    project_numbers = request.GET.getlist("pn")
    center_code = request.GET.get("center") or ""
    try:
        return get_bulk_projects_zip_response(project_numbers, center_code=center_code)
    except DownloadReviewJobRequestError as exc:
        response = JsonResponse(
            {"success": False, "message": str(exc)},
            status=exc.status_code,
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


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
