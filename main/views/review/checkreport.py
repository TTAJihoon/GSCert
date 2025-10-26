# -*- coding: utf-8 -*-
# GSCert/main/views/review/checkreport.py
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
import os

from .report_docx_parser import parse_docx   # 실제 파서 사용
from .report_pdf_parser  import parse_pdf    # 실제 파서 사용
from .checkreport_GPT import run_checkreport_gpt

@csrf_exempt
def parse_view(request: HttpRequest):
    """
    단일 엔드포인트(A안): 업로드(docx+pdf) → 파싱 → (합쳐진 JSON 전체) → GPT → 테이블 스키마 JSON
    - 디버그: 'X-Debug-GPT: 1' 헤더 또는 '?debug=1' 쿼리/POST가 있으면,
      응답에 '_debug': {
        'gpt_input': <합쳐진 원본 전체 JSON>,
        'gpt_request': <OpenAI에 실제로 보낸 요청 본문 전체>,
        'gpt_response_meta': <id/model/usage 등 요약>
      } 를 포함하여 브라우저 개발자도구에서 확인 가능.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only."}, status=405)

    debug_flag = (
        request.headers.get("X-Debug-GPT") == "1" or
        request.GET.get("debug") == "1" or
        request.POST.get("debug") == "1"
    )

    # 업로드: docx/pdf 각각 1개 고정
    docx_file = request.FILES.get("docx")
    pdf_file  = request.FILES.get("pdf")

    # 구 방식 호환
    if docx_file is None or pdf_file is None:
        files = request.FILES.getlist("file")
        for f in files:
            name = (getattr(f, "name", "") or "").lower()
            _, ext = os.path.splitext(name)
            if ext == ".docx" and docx_file is None:
                docx_file = f
            elif ext == ".pdf" and pdf_file is None:
                pdf_file = f

    if docx_file is None or pdf_file is None:
        return JsonResponse({"version": "1", "total": 0, "items": []})

    # 안전: 스트림 포인터 초기화
    try:
        if hasattr(docx_file, "seek"): docx_file.seek(0)
        if hasattr(pdf_file, "seek"):  pdf_file.seek(0)
    except Exception:
        pass

    # 1) 파싱 (각 파서가 반환하는 전체 JSON을 그대로 받음)
    try:
        docx_json = parse_docx(docx_file)
    except Exception as e:
        return JsonResponse({"error": f"DOCX parse failed: {e}"}, status=500)

    try:
        pdf_json = parse_pdf(pdf_file)
    except Exception as e:
        return JsonResponse({"error": f"PDF parse failed: {e}"}, status=500)

    # 2) 합쳐진 JSON (원본 전체) — 축약/발췌 없이 그대로
    combined = {
        "v": "1",
        "document": {
            "docx": docx_json,
            "pdf":  pdf_json
        }
    }

    # 3) GPT 분석 (debug_flag를 전달)
    result, gpt_debug = run_checkreport_gpt(combined, debug=debug_flag)

    # 4) 디버그 요구 시, GPT 입력/요청/응답메타 에코
    if debug_flag:
        result = dict(result)  # shallow copy
        result["_debug"] = {
            "gpt_input": combined,          # 우리가 GPT에 전달한 합쳐진 원본 전체 JSON
            **gpt_debug                     # gpt_request, gpt_response_meta
        }

    # 5) 최종 반환
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})
