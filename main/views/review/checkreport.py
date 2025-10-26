# -*- coding: utf-8 -*-
"""
checkreport.py
- /parse/ 엔드포인트: docx + pdf 동시 업로드 받아 파싱 결과 결합
- DOCX: report_docx_parser.parse_docx()
- PDF : report_pdf_parser.parse_pdf()
- 둘 중 하나라도 없으면 400
"""

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt

from .report_docx_parser import parse_docx   # 함수명 유지
from .report_pdf_parser import parse_pdf     # 함수명 유지

import os

@csrf_exempt
def parse_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only."}, status=405)

    files = request.FILES.getlist("file")  # 같은 키로 2개 올라옴
    if not files:
        return JsonResponse({"error": "Both 'docx' and 'pdf' files are required."}, status=400)

    docx_file = None
    pdf_file = None

    for f in files:
        name = getattr(f, "name", "") or ""
        ext = os.path.splitext(name.lower())[1]
        if ext == ".docx":
            docx_file = f
        elif ext == ".pdf":
            pdf_file = f

    if docx_file is None or pdf_file is None:
        return JsonResponse({"error": "Both 'docx' and 'pdf' files are required."}, status=400)

    # --- 파싱 ---
    try:
        docx_json = parse_docx(docx_file)  # {"v":"1","content":[...]}
    except Exception as e:
        return JsonResponse({"error": f"DOCX parse failed: {e}"}, status=500)

    try:
        pdf_json = parse_pdf(pdf_file)     # {"v":"1","total_pages":N,"pages":[...]}
    except Exception as e:
        return JsonResponse({"error": f"PDF parse failed: {e}"}, status=500)

    # --- 결합 ---
    out = {
        "v": "1",
        "docx": {
            "v": "1",
            "content": docx_json.get("content", []),
        },
        "pdf": pdf_json
    }
    return JsonResponse(out, json_dumps_params={"ensure_ascii": False})
