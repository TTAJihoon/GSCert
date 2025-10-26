# -*- coding: utf-8 -*-
"""
report_pdf_parser.py

역할:
- PDF 각 페이지에서 '첫 줄 텍스트'를 header, '마지막 줄 텍스트'를 footer로 추출.
- 모든 문서가 상/하단 1줄 고정이라는 전제에 최적화.
- PyMuPDF(권장) 사용, 실패 시 pdfminer.six로 폴백.

반환 예:
{
  "v": "1",
  "total_pages": 12,
  "pages": [
    {"page": 1, "header": ["1/12 소프트웨어시험인증연구소"], "footer": ["시나몬 음성봇 ..."]},
    ...
  ]
}
"""
from __future__ import annotations
from typing import List, Dict
import re

# --------------------------
# 공통 유틸
# --------------------------

_WS_RE = re.compile(r"[ \t\u00A0\u2000-\u200B]+")

def _clean_line(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\r", "\n").replace("\xa0", " ")
    s = _WS_RE.sub(" ", s)
    s = "\n".join(ch.strip() for ch in s.splitlines())
    s = s.strip()
    return s

# --------------------------
# PyMuPDF 버전
# --------------------------

def _extract_with_pymupdf(pdf_bytes: bytes) -> Dict:
    import fitz  # pymupdf
    pages = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        total = doc.page_count
        for i in range(total):
            p = doc.load_page(i)
            # 줄 단위 텍스트
            blocks = p.get_text("blocks")  # [(x0,y0,x1,y1,text,block_no,...)...]
            # y0 기준 오름차순 정렬 → 화면 위에서 아래
            blocks.sort(key=lambda b: (round(b[1], 2), round(b[0], 2)))
            # 텍스트만 추출하여 빈 줄 제거
            lines = [_clean_line(b[4]) for b in blocks if _clean_line(b[4])]
            header = [lines[0]] if lines else []
            footer = [lines[-1]] if len(lines) > 1 else (header[:] if lines else [])
            pages.append({
                "page": i + 1,
                "header": header,
                "footer": footer
            })
    return {
        "v": "1",
        "total_pages": len(pages),
        "pages": pages
    }

# --------------------------
# pdfminer.six 폴백
# --------------------------

def _extract_with_pdfminer(pdf_bytes: bytes) -> Dict:
    from io import BytesIO
    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams
    pages = []
    laparams = LAParams()
    # pdfminer의 extract_text는 한 번에 뽑는 편이라 페이지 분리를 위해 LAParams + page_numbers 루프 사용 권장
    # 하지만 간단화를 위해 한 번에 뽑고 '\x0c'(form feed)로 페이지 분리 처리
    text_all = extract_text(BytesIO(pdf_bytes), laparams=laparams) or ""
    split = [t for t in text_all.split("\f")]
    total = len(split) if split and split[-1] == "" else len(split)
    for idx, raw in enumerate(split[:total]):
        lines = [_clean_line(x) for x in raw.splitlines() if _clean_line(x)]
        header = [lines[0]] if lines else []
        footer = [lines[-1]] if len(lines) > 1 else (header[:] if lines else [])
        pages.append({
            "page": idx + 1,
            "header": header,
            "footer": footer
        })
    return {
        "v": "1",
        "total_pages": len(pages),
        "pages": pages
    }

# --------------------------
# 진입점
# --------------------------

def extract_header_footer_lines(pdf_bytes: bytes) -> Dict:
    """
    권장: PyMuPDF 사용.
    미설치/실패 시 pdfminer로 폴백.
    """
    try:
        return _extract_with_pymupdf(pdf_bytes)
    except Exception:
        return _extract_with_pdfminer(pdf_bytes)
