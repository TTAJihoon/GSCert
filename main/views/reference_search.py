from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from main.models import SwData

MAX_QUERY_LENGTH = 100
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@require_GET
def reference_search(request):
    q = (request.GET.get("q") or "").strip()
    try:
        limit = min(int(request.GET.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT

    if not q or len(q) < 2:
        return JsonResponse({"success": True, "items": [], "query": q})

    if len(q) > MAX_QUERY_LENGTH:
        return JsonResponse(
            {"success": False, "message": f"검색어는 {MAX_QUERY_LENGTH}자 이하여야 합니다."},
            status=400,
        )

    qs = (
        SwData.objects.using("reference")
        .filter(
            Q(company__icontains=q)
            | Q(product__icontains=q)
            | Q(cert_number__icontains=q)
            | Q(test_number__icontains=q)
        )
        .values(
            "serial_number",
            "cert_number",
            "cert_date",
            "company",
            "product",
            "grade",
            "test_number",
            "sw_category",
            "start_date",
            "end_date",
        )
        .order_by("-cert_date", "company")[:limit]
    )

    return JsonResponse({"success": True, "items": list(qs), "query": q})
