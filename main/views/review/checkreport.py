# -*- coding: utf-8 -*-
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from tempfile import NamedTemporaryFile
import json
import os

# 동일 디렉토리(또는 파이썬 경로)에 배치된 파서 모듈을 import
from .report_docx_parser import build_tree as build_docx_tree
from .report_pdf_parser import extract_headfoot as build_pdf_headfoot


@csrf_exempt
@require_POST
def parse_docx_pdf(request):
    """
    브라우저에서 docx + pdf 동시 업로드 → 두 JSON을 결합해 반환.
    - 둘 중 하나라도 누락되면 400 에러
    - 반환 구조:
      {
        "v": "1",
        "docx": {"v":"1","content":[ ... ]},
        "pdf":  {"v":"1","total_pages":N,"pages":[{"page":1,"header":[...],"footer":[...]}, ...]}
      }
    """
    docx_file = request.FILES.get("docx")
    pdf_file  = request.FILES.get("pdf")

    if not docx_file or not pdf_file:
        return HttpResponseBadRequest("Both 'docx' and 'pdf' files are required.")

    # 임시 저장
    tmp_docx = NamedTemporaryFile(delete=False, suffix=".docx")
    tmp_pdf  = NamedTemporaryFile(delete=False, suffix=".pdf")
    try:
        for chunk in docx_file.chunks():
            tmp_docx.write(chunk)
        tmp_docx.flush()

        for chunk in pdf_file.chunks():
            tmp_pdf.write(chunk)
        tmp_pdf.flush()

        # 파서 호출
        docx_json = build_docx_tree(tmp_docx.name)
        pdf_json  = build_pdf_headfoot(tmp_pdf.name)

        # 최종 결합
        result = {
            "v": "1",
            "docx": docx_json,
            "pdf": pdf_json,
        }
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False})
    finally:
        try:
            tmp_docx.close()
            os.unlink(tmp_docx.name)
        except Exception:
            pass
        try:
            tmp_pdf.close()
            os.unlink(tmp_pdf.name)
        except Exception:
            pass
