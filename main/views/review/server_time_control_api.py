from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from main.server_time_control import (
    ServerTimeRequestError,
    get_control,
    parse_request_body,
    public_payload,
    request_action,
)


def _response(payload, *, status=200):
    response = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def server_time_status(request):
    return _response(public_payload(get_control()))


@require_POST
def server_time_action(request):
    try:
        payload = parse_request_body(request)
        result = request_action(
            action=payload.get("action"),
            revision=payload.get("revision"),
            owner_name=payload.get("owner_name"),
            pin=payload.get("pin"),
            target_value=payload.get("target_time"),
            requested_ip=request.META.get("REMOTE_ADDR"),
        )
        return _response(result, status=202)
    except ServerTimeRequestError as exc:
        return _response({"success": False, "error_code": exc.code, "message": str(exc)}, status=exc.status_code)
