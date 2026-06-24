from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from main.views.review.ecm_download_review_centers import (
    allowed_centers_for_host,
    center_routes_for_host,
    default_center_for_host,
    is_center_allowed_for_host,
    normalize_center_code,
)

@login_required
def welcome(request):
    return render(request, 'welcome.html')

def login_test_view(request):
    return render(request, 'registration/login.html')

def index(request):
    return render(request, 'index.html')


def history(request):
    return render(request, 'testing/history.html')

def similar(request):
    return render(request, 'testing/similar.html')
    
def security(request):
    return render(request, 'testing/security.html')


def prdinfo(request):
    return render(request, 'certy/prdinfo.html')


def checkreport(request):
    return render(request, 'review/checkreport.html')
    
def test(request):
    return render(request, 'test.html')

@ensure_csrf_cookie
def download_review(request):
    host = request.get_host()
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

    return render(
        request,
        'review/ecm_download_review.html',
        {
            "download_review_default_center": center,
            "download_review_allowed_centers": sorted(allowed_centers_for_host(host)),
            "download_review_center_routes": center_routes_for_host(host),
        },
    )
