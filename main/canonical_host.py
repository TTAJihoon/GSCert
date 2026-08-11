from ipaddress import ip_address

from django.conf import settings
from django.http import HttpResponse


class CanonicalDomainRedirectMiddleware:
    """Redirect literal-IP hosts to the configured public domain."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical_domain = str(getattr(settings, "SERVER_DOMAIN", "") or "").strip()
        host = _host_without_port(request.get_host())
        if canonical_domain and _is_ip_address(host):
            response = HttpResponse(status=308)
            response["Location"] = f"https://{canonical_domain}{request.get_full_path()}"
            return response
        return self.get_response(request)


def _is_ip_address(value: str) -> bool:
    try:
        ip_address(value)
        return True
    except ValueError:
        return False


def _host_without_port(value: str) -> str:
    host = str(value or "").strip()
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host
