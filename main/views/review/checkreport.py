# checkreport.py

from __future__ import annotations
import json
from typing import Tuple, Optional
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt

from .report_docx_parser import parse_docx_to_json
from .report_pdf_parser import extract_header_footer_lines


def _read_fileobj(f) -> Optional[bytes]:
    if not f:
        return None
    try:
        data = f.read()
        return data if data else None
    except Exception:
        return None


def _pick_files(request: HttpRequest) -> Tuple[bytes, bytes]:
    """
    1순위: 필드명이 'docx', 'pdf'인 업로드
    2순위: 같은 이름 'file'로 2개 올라온 업로드
    실패 시 ValueError
    """
    # 1) 명시 필드 우선
    docx_bytes = _read_fileobj(request.FILES.get("docx"))
    pdf_bytes  = _read_fileobj(request.FILES.get("pdf"))

    # 2) 하위호환: 같은 키(file) 2개
    if not (docx_bytes and pdf_bytes):
        files = request.FILES.getlist("file")
        for f in files:
            name = (getattr(f, "name", "") or "").lower()
            data = _read_fileobj(f)
            if not data:
                continue
            if name.endswith(".docx") and not docx_bytes:
                docx_bytes = data
            elif name.endswith(".pdf") and not pdf_bytes:
                pdf_bytes = data

    missing = []
    if not docx_bytes:
        missing.append("docx")
    if not pdf_bytes:
        missing.append("pdf")
    if missing:
        raise ValueError(f"Missing required uploads: {', '.join(missing)}")

    return docx_bytes, pdf_bytes


@csrf_exempt
def parse_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        docx_bytes, pdf_bytes = _pick_files(request)

        # DOCX 파싱 (문단/표/수식)
        docx_json = parse_docx_to_json(docx_bytes, with_paragraphs=True)

        # PDF 파싱 (페이지별 1줄 header/1줄 footer)
        pdf_json = extract_header_footer_lines(pdf_bytes)

        combined = {
            "v": "1",
            "docx": docx_json.get("docx", {"v": "1", "content": []}),
            "pdf": pdf_json,
        }
        return JsonResponse(combined, json_dumps_params={"ensure_ascii": False}, status=200)

    except ValueError as ve:
        # 사용자가 보아도 되는 친절한 400
        return JsonResponse({"error": str(ve)}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"{type(e).__name__}: {e}"}, status=500)
