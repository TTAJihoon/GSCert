from django.http import JsonResponse
from django.views.csrf import csrf_failure as default_csrf_failure


def csrf_failure(request, reason=""):
    wants_json = "application/json" in request.headers.get("Accept", "")
    is_api = request.path.startswith("/api/")
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_api or wants_json or is_xhr:
        response = JsonResponse(
            {
                "success": False,
                "error_code": "csrf_failed",
                "message": "보안 토큰 확인에 실패했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.",
            },
            status=403,
            json_dumps_params={"ensure_ascii": False},
        )
        response["Cache-Control"] = "no-store"
        return response
    return default_csrf_failure(request, reason=reason)
