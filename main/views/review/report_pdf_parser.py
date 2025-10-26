# -*- coding: utf-8 -*-
import pdfplumber
from math import isfinite

def _split_lines(s: str):
    if not s:
        return []
    return [line.strip() for line in s.splitlines() if line.strip()]

def _lines_from_words(words, y_tol=3.0):
    """
    pdfplumber.extract_words() 결과를 y좌표로 묶어 라인 문자열 배열로 변환
    """
    if not words:
        return []
    # y0(=bottom) 기준 오름차순 → 클러스터링
    words = [w for w in words if all(isfinite(w.get(k, 0)) for k in ("x0","x1","top","bottom"))]
    words.sort(key=lambda w: (w["top"], w["x0"]))
    lines = []
    current_y = None
    current = []
    for w in words:
        y = w["top"]
        if current_y is None or abs(y - current_y) <= y_tol:
            current.append(w)
            current_y = y if current_y is None else (current_y + y)/2.0
        else:
            current.sort(key=lambda t: t["x0"])
            lines.append(" ".join(t["text"] for t in current if t.get("text")))
            current = [w]
            current_y = y
    if current:
        current.sort(key=lambda t: t["x0"])
        lines.append(" ".join(t["text"] for t in current if t.get("text")))
    # 공백/빈줄 정리
    return [ln.strip() for ln in lines if ln.strip()]

def _extract_band_text(page, bbox):
    band = page.within_bbox(bbox)
    # 1) 기본 방법
    txt = band.extract_text(x_tolerance=1, y_tolerance=1) or ""
    lines = _split_lines(txt)
    if lines:
        return lines
    # 2) words 폴백
    words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
    x0, y0, x1, y1 = bbox
    words_band = [w for w in words if (w["bottom"] <= y1 and w["top"] >= y0 and w["x0"] >= x0 and w["x1"] <= x1)]
    return _lines_from_words(words_band)

def extract_headfoot(pdf_path: str, header_ratio: float = 0.07, footer_ratio: float = 0.07):
    """
    PDF 각 페이지의 상/하단 밴드(비율)에서 텍스트를 추출해 라인 배열로 반환.
    {
      "v":"1",
      "total_pages":N,
      "pages":[{"page":i,"header":[...],"footer":[...]},...]
    }
    """
    pages_out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            x0, y0, x1, y1 = page.bbox  # (left, bottom, right, top)
            height = y1 - y0
            h_h = max(1.0, height * header_ratio)
            f_h = max(1.0, height * footer_ratio)

            header_bbox = (x0, y1 - h_h, x1, y1)
            footer_bbox = (x0, y0,       x1, y0 + f_h)

            header_lines = _extract_band_text(page, header_bbox)
            footer_lines = _extract_band_text(page, footer_bbox)

            pages_out.append({
                "page": i,
                "header": header_lines,
                "footer": footer_lines
            })
    return {"v": "1", "total_pages": len(pages_out), "pages": pages_out}
