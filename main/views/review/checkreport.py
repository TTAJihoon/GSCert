# -*- coding: utf-8 -*-
# GSCert/main/views/review/checkreport.py
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
import os

from .report_docx_parser import parse_docx   # 함수명 유지
from .report_pdf_parser  import parse_pdf    # 함수명 유지
from .checkreport_GPT import run_checkreport_gpt

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

    # 최종 검증 (요구사항: docx + pdf 고정)
    if docx_file is None or pdf_file is None:
        return JsonResponse({"version": "1", "total": 0, "items": []})

    # 안전: 스트림 포인터 초기화
    try:
        if hasattr(docx_file, "seek"):
            docx_file.seek(0)
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
    except Exception:
        pass

    # 1) 파싱
    try:
        docx_json = parse_docx(docx_file)  # {"v":"1","content":[...]} 등
    except Exception as e:
        return JsonResponse({"error": f"DOCX parse failed: {e}"}, status=500)

    try:
        pdf_json = parse_pdf(pdf_file)     # {"v":"1","total_pages":N,"pages":[...]} 등
    except Exception as e:
        return JsonResponse({"error": f"PDF parse failed: {e}"}, status=500)

    parsed = {
        "v": "1",
        "docx": {"v": "1", "content": docx_json.get("content", [])},
        "pdf":  pdf_json,
        # 필요 시 여기에 규칙 기반 이슈 수집을 추가하여 {"issues":[...]}를 채울 수 있습니다.
        # 본 A안에서는 GPT가 전체 parsed를 받고 판단하도록 합니다.
    }

    # 2) GPT 분석 → 테이블 스키마
    result = run_checkreport_gpt(parsed)

    # 3) 최종 반환 (프런트 테이블용 스키마)
    # 데이터 없으면 빈 구조 → 프런트에서 emptyState 표시
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})
