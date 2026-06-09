import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone


REQUEST_LOG_CONTEXT_ATTR = "_gscert_log_context"
KST = timezone(timedelta(hours=9), "KST")

logger = logging.getLogger("gscert.request")


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

    if error:
        parts.append(f"error={_clean(error, max_length=80)}")
    if message:
        parts.append(f"message={_quote(message)}")

    context = getattr(request, REQUEST_LOG_CONTEXT_ATTR, {})
    for key in sorted(context):
        parts.append(f"{key}={_quote(context[key])}")

    return " | ".join(parts)


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
