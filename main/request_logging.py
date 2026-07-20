import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone


REQUEST_LOG_CONTEXT_ATTR = "_gscert_log_context"
KST = timezone(timedelta(hours=9), "KST")

logger = logging.getLogger("gscert.request")

# 이 문자열을 포함하는 파라미터 키는 값을 로그에 남기지 않고 마스킹한다.
_SENSITIVE_KEY_SUBSTRINGS = (
    "password", "passwd", "pwd", "token", "secret", "authorization",
    "credential", "csrfmiddlewaretoken", "apikey", "api_key",
)


class MaxLevelFilter(logging.Filter):
    """지정한 레벨보다 심각한(높은) 로그 레코드를 걸러낸다.

    stdout 핸들러가 ERROR/WARNING까지 함께 출력하지 않도록,
    handler의 최소 레벨(하한)과 짝을 이뤄 상한을 두는 용도로 쓴다.
    """

    def __init__(self, max_level):
        super().__init__()
        self.max_level = (
            logging.getLevelName(max_level) if isinstance(max_level, str) else max_level
        )

    def filter(self, record):
        return record.levelno <= self.max_level


def set_request_log_context(request, **fields):
    context = getattr(request, REQUEST_LOG_CONTEXT_ATTR, {})
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, str) and value == "":
            continue
        context[key] = value
    setattr(request, REQUEST_LOG_CONTEXT_ATTR, context)


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.gscert_request_id = request_id
        started = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception as exc:
            duration_ms = _duration_ms(started)
            logger.error(
                _format_log_line(
                    "ERROR",
                    request,
                    request_id=request_id,
                    status=500,
                    duration_ms=duration_ms,
                    error=exc.__class__.__name__,
                    message=str(exc),
                )
            )
            raise

        duration_ms = _duration_ms(started)
        response["X-Request-ID"] = request_id

        if response.status_code >= 500:
            logger.error(
                _format_log_line(
                    "ERROR",
                    request,
                    request_id=request_id,
                    status=response.status_code,
                    duration_ms=duration_ms,
                    error="HTTPError",
                    message=getattr(response, "reason_phrase", ""),
                )
            )
        elif response.status_code >= 400:
            # 4xx는 서버 예외는 아니지만 "에러"로 취급해 err.log로 보낸다.
            logger.warning(
                _format_log_line(
                    "ERROR",
                    request,
                    request_id=request_id,
                    status=response.status_code,
                    duration_ms=duration_ms,
                    error="ClientError",
                    message=getattr(response, "reason_phrase", ""),
                )
            )
        else:
            logger.info(
                _format_log_line(
                    "ACCESS",
                    request,
                    request_id=request_id,
                    status=response.status_code,
                    duration_ms=duration_ms,
                )
            )

        return response


def _duration_ms(started):
    return int((time.perf_counter() - started) * 1000)


def _format_log_line(event, request, *, request_id, status, duration_ms, error=None, message=None):
    parts = [
        event,
        _now(),
        f"request_id={request_id}",
        f"ip={_client_ip(request)}",
        f"method={request.method}",
        f"path={request.path}",
        f"status={status}",
        f"duration_ms={duration_ms}",
    ]

    feature = _resolve_feature(request)
    if feature:
        parts.append(f"feature={feature}")

    if error:
        parts.append(f"error={_clean(error, max_length=80)}")
    if message:
        parts.append(f"message={_quote(message)}")

    params = _collect_masked_params(request)
    if params:
        parts.append(f"params={_quote(params)}")

    context = getattr(request, REQUEST_LOG_CONTEXT_ATTR, {})
    for key in sorted(context):
        if key == "feature":
            continue  # 위에서 이미 출력함
        parts.append(f"{key}={_quote(context[key])}")

    return " | ".join(parts)


def _resolve_feature(request):
    """기능명을 결정한다: 뷰에서 수동으로 지정한 feature가 있으면 그것을 우선하고,
    없으면 Django가 URL 매칭 결과로 갖고 있는 view name/함수명을 자동으로 쓴다.
    """
    context = getattr(request, REQUEST_LOG_CONTEXT_ATTR, {})
    manual_feature = context.get("feature")
    if manual_feature:
        return manual_feature

    match = getattr(request, "resolver_match", None)
    if match is None:
        return None
    if match.view_name:
        return match.view_name
    func = getattr(match, "func", None)
    return getattr(func, "__name__", None)


def _is_sensitive_key(key):
    lowered = key.lower()
    return any(needle in lowered for needle in _SENSITIVE_KEY_SUBSTRINGS)


def _collect_masked_params(request):
    """GET 쿼리와 POST/JSON 바디를 합쳐 파라미터로 남긴다.
    비밀번호/토큰 등 민감한 키는 값을 마스킹하고, 업로드 파일은 이름/크기만 남긴다.
    """
    params = {}

    for key, value in request.GET.items():
        params[key] = "***" if _is_sensitive_key(key) else value

    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.META.get("CONTENT_TYPE", "")
        if "application/json" in content_type:
            try:
                body = json.loads(request.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = None
            if isinstance(body, dict):
                for key, value in body.items():
                    params[key] = "***" if _is_sensitive_key(key) else value
        else:
            for key, value in request.POST.items():
                params[key] = "***" if _is_sensitive_key(key) else value
            for key, uploaded_file in request.FILES.items():
                params[key] = f"<file:{uploaded_file.name},{uploaded_file.size}B>"

    return params


def _now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " KST"


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.META.get("HTTP_X_REAL_IP", "")
    if real_ip:
        return real_ip.strip()
    return request.META.get("REMOTE_ADDR", "-")


def _quote(value):
    return json.dumps(_clean(value), ensure_ascii=False)


def _clean(value, max_length=300):
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(item) for item in value)
    elif isinstance(value, dict):
        value = "; ".join(
            f"{key}={item}"
            for key, item in value.items()
            if item not in (None, "")
        )
    text = " ".join(str(value).split())
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text
