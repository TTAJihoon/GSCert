# -*- coding: utf-8 -*-
import pdfplumber

def _split_lines(s: str):
    if not s:
        return []
    # 줄단위 분할 + 좌우공백 제거 + 빈줄 제거
    return [line.strip() for line in s.splitlines() if line.strip()]

def extract_headfoot(pdf_path: str, header_ratio: float = 0.07, footer_ratio: float = 0.07):
    """
    PDF에서 각 페이지의 상단/하단 비율 영역만 텍스트 추출하여 반환.
    {
      "v": "1",
      "total_pages": N,
      "pages": [
        {"page": 1, "header": ["..."], "footer": ["..."]},
        ...
      ]
    }
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            x0, y0, x1, y1 = page.bbox  # (left, bottom, right, top)
            height = y1 - y0
            h_h = height * header_ratio
            f_h = height * footer_ratio

            # header 영역: 상단 h_h
            header_crop = page.within_bbox((x0, y1 - h_h, x1, y1))
            header_text = header_crop.extract_text(x_tolerance=1, y_tolerance=1) or ""
            header_lines = _split_lines(header_text)

            # footer 영역: 하단 f_h
            footer_crop = page.within_bbox((x0, y0, x1, y0 + f_h))
            footer_text = footer_crop.extract_text(x_tolerance=1, y_tolerance=1) or ""
            footer_lines = _split_lines(footer_text)

            pages.append({
                "page": i,
                "header": header_lines,
                "footer": footer_lines
            })

    return {"v": "1", "total_pages": len(pages), "pages": pages}
