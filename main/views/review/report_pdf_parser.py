# -*- coding: utf-8 -*-
import pdfplumber
from math import isfinite

# 많은 페이지에서 상단이 비고 하단만 채워졌다면 header<->footer를 전체 스왑
REPEAT_SWAP_THRESHOLD = 0.6  # 60%

def _split_lines(s: str):
    if not s:
        return []
    return [line.strip() for line in s.splitlines() if line.strip()]

def _lines_from_words(words, x0, y0, x1, y1, y_tol=3.0):
    """extract_words() 결과를 bbox 내부로 필터링 후 y군집 → 한 줄 문자열 배열"""
    if not words:
        return []
    band = [
        w for w in words
        if all(isfinite(w.get(k, 0)) for k in ("x0","x1","top","bottom"))
        and (w["bottom"] <= y1 and w["top"] >= y0 and w["x0"] >= x0 and w["x1"] <= x1)
    ]
    if not band:
        return []
    band.sort(key=lambda w: (w["top"], w["x0"]))
    lines, current, current_y = [], [], None
    for w in band:
        y = w["top"]
        if current_y is None or abs(y - current_y) <= y_tol:
            current.append(w)
            current_y = y if current_y is None else (current_y + y) / 2.0
        else:
            current.sort(key=lambda t: t["x0"])
            lines.append(" ".join(t["text"] for t in current if t.get("text")))
            current, current_y = [w], y
    if current:
        current.sort(key=lambda t: t["x0"])
        lines.append(" ".join(t["text"] for t in current if t.get("text")))
    return [ln.strip() for ln in lines if ln.strip()]

def _extract_band_lines(page, bbox):
    band = page.within_bbox(bbox)
    # 1) 기본 추출
    txt = band.extract_text(x_tolerance=1, y_tolerance=1) or ""
    lines = _split_lines(txt)
    if lines:
        return lines
    # 2) words 폴백
    words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
    x0, y0, x1, y1 = bbox
    return _lines_from_words(words, x0, y0, x1, y1)

def extract_headfoot(pdf_path: str, header_ratio: float = 0.07, footer_ratio: float = 0.09):
    """
    상단 header_ratio(기본 7%), 하단 footer_ratio(기본 9%) 밴드에서 텍스트 추출.
    좌표계: y는 아래->위로 증가하므로, 헤더는 (y1 - h_h ~ y1), 푸터는 (y0 ~ y0 + f_h).
    반환:
      { "v":"1", "total_pages":N,
        "pages":[{"page":1,"header":[...],"footer":[...]}, ...] }
    """
    pages_out = []
    header_empty_footer_nonempty = 0

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            x0, y0, x1, y1 = page.bbox
            height = y1 - y0
            h_h = max(1.0, height * header_ratio)
            f_h = max(1.0, height * footer_ratio)

            # 헤더: 상단 7%
            header_bbox = (x0, y1 - h_h, x1, y1)
            # 푸터: 하단 9%
            footer_bbox = (x0, y0, x1, y0 + f_h)

            header_lines = _extract_band_lines(page, header_bbox)
            footer_lines = _extract_band_lines(page, footer_bbox)

            if not header_lines and footer_lines:
                header_empty_footer_nonempty += 1

            pages_out.append({
                "page": i,
                "header": header_lines,
                "footer": footer_lines
            })

    # 반복성 스왑: 문서 특성상 상단이 늘 비고 하단만 반복될 때 뒤바뀐 추출을 교정
    total = len(pages_out) or 1
    if header_empty_footer_nonempty / total >= REPEAT_SWAP_THRESHOLD:
        for p in pages_out:
            p["header"], p["footer"] = p["footer"], p["header"]

    return {"v": "1", "total_pages": len(pages_out), "pages": pages_out}
