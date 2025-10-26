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
    - GPT로 전달되는 JSON은 '제한 없이' 원본 전체를 그대로 보냅니다(발췌/축약 없음).
    - 프런트는 결과가 0개면 emptyState, 있으면 테이블을 표시합니다.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only."}, status=405)

    # 업로드: docx/pdf 각각 1개 고정 (요구사항)
    docx_file = request.FILES.get("docx")
    pdf_file  = request.FILES.get("pdf")

    # 구 방식(같은 name으로 2개 업로드) 호환
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
        # 프런트는 이 값을 받아 emptyState를 보여줌
        return JsonResponse({"version": "1", "total": 0, "items": []})

    # 안전: 스트림 포인터 초기화
    try:
        if hasattr(docx_file, "seek"): docx_file.seek(0)
        if hasattr(pdf_file, "seek"):  pdf_file.seek(0)
    except Exception:
        pass

    # 1) 파싱 (각 파서가 반환하는 전체 JSON을 그대로 받습니다)
    try:
        docx_json = parse_docx(docx_file)  # 예: {"v":"1","content":[...], ...}
    except Exception as e:
        return JsonResponse({"error": f"DOCX parse failed: {e}"}, status=500)

    try:
        pdf_json = parse_pdf(pdf_file)     # 예: {"v":"1","total_pages":N,"pages":[...], ...}
    except Exception as e:
        return JsonResponse({"error": f"PDF parse failed: {e}"}, status=500)

    # 2) 합쳐진 JSON(원본 전체) 생성 — 어떤 축약/발췌도 하지 않음
    #    필요한 경우, 통합 키를 'document' 하나로 쓰고 내부에 docx/pdf를 그대로 둡니다.
    combined = {
        "v": "1",
        "document": {
            "docx": docx_json,   # 원본 전체
            "pdf":  pdf_json     # 원본 전체
        }
    }

    # 3) GPT 분석: 합쳐진 JSON 전체를 그대로 전달
    result = run_checkreport_gpt(combined)

    # 4) 최종 반환(테이블 스키마)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})
