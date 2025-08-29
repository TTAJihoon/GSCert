from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
import io

from .prdinfo_extractors import (
    extract_process1_docx_basic,
    extract_process2_docx_overview,
    extract_process3_xlsx_defects,
    build_fill_map,
)

ALLOWED_MAX_FILES = 3

def _classify_files(files):
    """
    업로드된 파일 중 1/2/3번 대상 선별:
    - 1번: '합의서' 포함 .docx
    - 2번: '성적서' 포함 .docx
    - 3번: '결함리포트' 또는 '결함' 포함 .xlsx
    """
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

    # 1번: 합의서(.docx)
    list1 = []
    for f in p1_files[:1]:
        try:
            b = io.BytesIO(f.read())
            result = extract_process1_docx_basic(b, f.name)
            list1.append(result)
        except Exception:
            list1.append(f"({f.name}) 내용에 문제가 있습니다")

    # 2번: 성적서(.docx)
    list2 = []
    for f in p2_files[:1]:
        try:
            b = io.BytesIO(f.read())
            result = extract_process2_docx_overview(b, f.name)
            list2.append(result)
        except Exception:
            list2.append(f"({f.name}) 내용에 문제가 있습니다")

    # 3번: 결함리포트(.xlsx)
    list3 = []
    for f in p3_files[:1]:
        try:
            b = io.BytesIO(f.read())
            result = extract_process3_xlsx_defects(b, f.name)
            list3.append(result)
        except Exception:
            list3.append(f"({f.name}) 내용에 문제가 있습니다")

    # fillMap 구성
    obj1 = next((x for x in list1 if isinstance(x, dict)), None) or {}
    obj2 = next((x for x in list2 if isinstance(x, dict)), None) or {}
    obj3 = next((x for x in list3 if isinstance(x, dict)), None) or {}

    fill_map = build_fill_map(obj1, obj2, obj3)
    gs_number = obj1.get("시험신청번호", "") if isinstance(obj1, dict) else ""
    
    """
    요청: multipart/form-data, key='file' * 3개
    응답(JSON):
    {
      "list1": [...],  # 1번 과정 결과 리스트
      "list2": [...],  # 2번 과정 결과 리스트
      "list3": [...],  # 3번 과정 결과 리스트
      "fillMap": {     # Luckysheet 입력용
         "제품 정보 요청": { "A1": "...", ... },
         "결함정보":     { "B4": 3, ... }
      },
      "gsNumber": "GS-B-25-0079"  # (있으면) 파일명에 사용할 값
    }
    """
    
    return JsonResponse({
        "list1": list1,
        "list2": list2,
        "list3": list3,
        "fillMap": fill_map,
        "gsNumber": gs_number or ""
    })
