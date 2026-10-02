from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from main.views.review.ecm_download_review_centers import (
    allowed_centers_for_host,
    center_routes_for_host,
    default_center_for_client_ip,
    default_center_for_host,
    is_center_allowed_for_host,
    normalize_center_code,
)

@login_required
def welcome(request):
    return render(request, 'welcome.html')

def login_test_view(request):
    return render(request, 'registration/login.html')

def history(request):
    return render(request, 'testing/history.html')

def similar(request):
    return render(request, 'testing/similar.html')
    
def security(request):
    return render(request, 'testing/security.html')


def consultation(request):
    return render(request, 'consultation.html')


def prdinfo(request):
    return render(request, 'certy/prdinfo.html')


def checkreport(request):
    return render(request, 'review/checkreport.html')
    
def test(request):
    return render(request, 'test.html')

@ensure_csrf_cookie
def download_review(request):
    return _download_review_response(request)


@ensure_csrf_cookie
def kolas_review(request):
    """KOLAS 점검 페이지(/kolas/). ECM 점검 페이지 템플릿/JS 를 재사용하되 별도 프로젝트 목록을 쓴다."""
    return _download_review_response(request, kolas=True)


def _download_review_response(request, kolas=False):
    host = request.get_host()
    default_center = default_center_for_client_ip(_client_ip(request)) or default_center_for_host(host)
    if not is_center_allowed_for_host(default_center, host):
        default_center = default_center_for_host(host)
    requested_center = request.GET.get("center")
    if requested_center:
        try:
            requested_center = normalize_center_code(requested_center)
        except ValueError:
            requested_center = default_center
    center = requested_center or default_center
    if not is_center_allowed_for_host(center, host):
        center = default_center

    center_routes = center_routes_for_host(host)
    context = {
        "download_review_default_center": center,
        "download_review_allowed_centers": sorted(allowed_centers_for_host(host)),
        "download_review_center_routes": center_routes,
    }
    if kolas:
        # 다른 서버로 넘기는 센터 라우트도 ECM 점검 페이지가 아니라 그 서버의 KOLAS 페이지로 보낸다.
        context["download_review_center_routes"] = {
            code: url.replace("/download-review/", "/kolas/") if url else url
            for code, url in center_routes.items()
        }
        context["kolas_mode"] = True
        context["kolas_report_max_projects"] = getattr(settings, "KOLAS_REPORT_MAX_PROJECTS", 500)

    return render(request, 'review/ecm_download_review.html', context)


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return real_ip.strip()
    return request.META.get("REMOTE_ADDR")
