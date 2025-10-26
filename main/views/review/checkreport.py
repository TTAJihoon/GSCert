# -*- coding: utf-8 -*-
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
import os

from .report_docx_parser import parse_docx   # 함수명 유지
from .report_pdf_parser  import parse_pdf    # 함수명 유지

@csrf_exempt
def parse_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only."}, status=405)

    # 1) 새 방식: 서로 다른 키로 업로드 (docx, pdf)
    docx_file = request.FILES.get("docx")
    pdf_file  = request.FILES.get("pdf")

    # 2) 구 방식: 같은 키("file")로 2개 업로드 → 확장자로 구분
    if docx_file is None or pdf_file is None:
        files = request.FILES.getlist("file")
        for f in files:
            name = (getattr(f, "name", "") or "").lower()
            _, ext = os.path.splitext(name)
            if ext == ".docx" and docx_file is None:
                docx_file = f
            elif ext == ".pdf" and pdf_file is None:
                pdf_file = f

    # 최종 검증
    if docx_file is None or pdf_file is None:
        return JsonResponse({"error": "Both 'docx' and 'pdf' files are required."}, status=400)

    # 안전: 스트림 포인터 초기화
    try:
        if hasattr(docx_file, "seek"):
            docx_file.seek(0)
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
    except Exception:
        pass

    # 파싱
    try:
        docx_json = parse_docx(docx_file)  # {"v":"1","content":[...]}
    except Exception as e:
        return JsonResponse({"error": f"DOCX parse failed: {e}"}, status=500)

    try:
        pdf_json = parse_pdf(pdf_file)     # {"v":"1","total_pages":N,"pages":[...]}
    except Exception as e:
        return JsonResponse({"error": f"PDF parse failed: {e}"}, status=500)

    out = {
        "v": "1",
        "docx": {"v": "1", "content": docx_json.get("content", [])},
        "pdf": pdf_json,
    }
    return JsonResponse(out, json_dumps_params={"ensure_ascii": False})
