from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
import io

from .prdinfo_parse_agreement import extract_process1_docx_basic
from .prdinfo_parse_report import extract_process2_docx_overview
from .prdinfo_parse_defects import extract_process3_xlsx_defects
from .prdinfo_fillmap import build_fill_map

ALLOWED_MAX_FILES = 3

def _classify_files(files):
    p1, p2, p3 = [], [], []
    for f in files:
        name = (f.name or "").lower()
        if ("합의서" in name) and name.endswith(".docx"):
            p1.append(f)
        elif ("성적서" in name) and name.endswith(".docx"):
            p2.append(f)
        elif (("결함리포트" in name) or ("결함" in name)) and name.endswith(".xlsx"):
            p3.append(f)
    return p1, p2, p3

@require_POST
def generate_prdinfo(request):
    files = request.FILES.getlist("file")
    if not files:
        return HttpResponseBadRequest("파일이 없습니다.")
    if len(files) > ALLOWED_MAX_FILES:
        return HttpResponseBadRequest("파일은 최대 3개까지 업로드할 수 있습니다.")

    p1_files, p2_files, p3_files = _classify_files(files)

    list1, list2, list3 = [], [], []

    for f in p1_files[:1]:
        try:
            result = extract_process1_docx_basic(io.BytesIO(f.read()), f.name)
            list1.append(result)
        except Exception:
            list1.append(f"({f.name}) 내용에 문제가 있습니다")

    for f in p2_files[:1]:
        try:
            result = extract_process2_docx_overview(io.BytesIO(f.read()), f.name)
            list2.append(result)
        except Exception:
            list2.append(f"({f.name}) 내용에 문제가 있습니다")

    for f in p3_files[:1]:
        try:
            result = extract_process3_xlsx_defects(io.BytesIO(f.read()), f.name)
            list3.append(result)
        except Exception:
            list3.append(f"({f.name}) 내용에 문제가 있습니다")

    obj1 = next((x for x in list1 if isinstance(x, dict)), None) or {}
    obj2 = next((x for x in list2 if isinstance(x, dict)), None) or {}
    obj3 = next((x for x in list3 if isinstance(x, dict)), None) or {}

    fill_map = build_fill_map(obj1, obj2, obj3)
    gs_number = obj1.get("시험신청번호", "") if isinstance(obj1, dict) else ""

    return JsonResponse({
        "list1": list1,
        "list2": list2,
        "list3": list3,
        "fillMap": fill_map,
        "gsNumber": gs_number or ""
    })
