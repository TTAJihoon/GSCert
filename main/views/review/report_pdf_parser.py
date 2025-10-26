# -*- coding: utf-8 -*-
import pdfplumber
from math import isfinite

def _cluster_words_to_lines(words, y_tol=3.0):
    """
    pdfplumber.extract_words() → y좌표로 클러스터링하여 라인화.
    return: [{'top': float, 'bottom': float, 'x0': float, 'x1': float, 'text': str}, ...]
    """
    words = [
        w for w in (words or [])
        if w.get("text")
        and all(isfinite(w.get(k, 0)) for k in ("x0", "x1", "top", "bottom"))
    ]
    if not words:
        return []

    # y(위치)→x(좌) 정렬
    words.sort(key=lambda w: (w["top"], w["x0"]))

    lines = []
    cur, cur_top, cur_bottom = [], None, None
    for w in words:
        y = w["top"]
        if cur_top is None or abs(y - cur_top) <= y_tol:
            cur.append(w)
            cur_top    = y if cur_top is None else (cur_top + y) / 2.0
            cur_bottom = w["bottom"] if cur_bottom is None else max(cur_bottom, w["bottom"])
        else:
            cur.sort(key=lambda t: t["x0"])
            text = " ".join(t["text"] for t in cur if t.get("text")).strip()
            if text:
                lines.append({
                    "top": cur_top,
                    "bottom": cur_bottom,
                    "x0": cur[0]["x0"],
                    "x1": cur[-1]["x1"],
                    "text": text,
                })
            cur, cur_top, cur_bottom = [w], y, w["bottom"]

    if cur:
        cur.sort(key=lambda t: t["x0"])
        text = " ".join(t["text"] for t in cur if t.get("text")).strip()
        if text:
            lines.append({
                "top": cur_top,
                "bottom": cur_bottom,
                "x0": cur[0]["x0"],
                "x1": cur[-1]["x1"],
                "text": text,
            })
    return lines


def extract_headfoot(pdf_path: str):
    """
    각 페이지에서 '가장 위 라인 1개'를 header, '가장 아래 라인 1개'를 footer로 채택.
    - 문서가 '상·하단 1줄 고정'이라는 전제를 사용
    - 반환 스키마는 동일하게 유지(header/footer는 1줄짜리 배열)
    {
      "v": "1",
      "total_pages": N,
      "pages": [
        {"page": 1, "header": ["..."], "footer": ["..."]},
        ...
      ]
    }
    """
    pages_out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
            lines = _cluster_words_to_lines(words, y_tol=3.0)

            if not lines:
                pages_out.append({"page": i, "header": [], "footer": []})
                continue

            # 좌표계: y는 아래→위로 증가
            # 최상단 라인: 'top'이 가장 큰 것
            header_line = max(lines, key=lambda ln: ln["top"])
            # 최하단 라인: 'bottom'이 가장 작은 것 (혹은 'top'이 가장 작은 것) 중 하나 사용
            footer_line = min(lines, key=lambda ln: ln["bottom"])

            pages_out.append({
                "page": i,
                "header": [header_line["text"]] if header_line and header_line.get("text") else [],
                "footer": [footer_line["text"]] if footer_line and footer_line.get("text") else [],
            })

    return {"v": "1", "total_pages": len(pages_out), "pages": pages_out}
