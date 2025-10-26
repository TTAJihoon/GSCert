# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import os
import tempfile
from typing import Tuple
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt

# 같은 디렉터리(또는 pythonpath)에 두 파일이 있어야 함
from .report_docx_parser import parse_docx_to_json
from .report_pdf_parser import extract_header_footer_lines


def _pick_files(files) -> Tuple[bytes, bytes]:
    """
    <input name="file" multiple> 로 올라온 2개 중 확장자로 DOCX/PDF 구분.
    반환: (docx_bytes, pdf_bytes)
    예외: 갯수/형식 오류 시 ValueError
    """
    if not files:
        raise ValueError("Both 'docx' and 'pdf' files are required.")

    docx_bytes = None
    pdf_bytes = None

    for f in files:
        name = (getattr(f, "name", "") or "").lower()
        data = f.read()
        if name.endswith(".docx"):
            docx_bytes = data
        elif name.endswith(".pdf"):
            pdf_bytes = data

    if not docx_bytes or not pdf_bytes:
        raise ValueError("Both 'docx' and 'pdf' files are required.")

    return docx_bytes, pdf_bytes


@csrf_exempt
def parse_view(request: HttpRequest):
    """
    POST /parse/
    - form-data field: file (2개: docx + pdf)
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        files = request.FILES.getlist("file")
        docx_bytes, pdf_bytes = _pick_files(files)

        # ---- DOCX 파싱 (문단+표, 수식 선형화 포함) ----
        docx_json = parse_docx_to_json(docx_bytes, with_paragraphs=True)

        # ---- PDF 파싱 (페이지별 1줄 header/footer) ----
        pdf_json = extract_header_footer_lines(pdf_bytes)

        # ---- 최종 결합 (2.3에서 합의한 방식) ----
        # v/meta는 의미 없다고 했으므로 최소화. v는 placeholder로 둠.
        combined = {
            "v": "1",
            "docx": docx_json.get("docx", {"v": "1", "content": []}),
            "pdf": pdf_json  # {"v":"1","total_pages":...,"pages":[...]}
        }

        return JsonResponse(combined, json_dumps_params={"ensure_ascii": False}, status=200)

    except ValueError as ve:
        return JsonResponse({"error": str(ve)}, status=400)
    except Exception as e:
        # 디버깅 편의를 위해 메시지 노출 (운영에선 로깅 후 일반 메시지 권장)
        return JsonResponse({"error": f"{type(e).__name__}: {e}"}, status=500)
