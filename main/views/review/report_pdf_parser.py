# -*- coding: utf-8 -*-
"""
report_pdf_parser.py
- PDF 각 페이지에서 상/하단 '1줄'만 추출
- header: 페이지 최상단(최대 y1)의 한 줄
- footer: 페이지 최하단(최소 y0)의 한 줄
- 반환: {"v":"1","total_pages":N,"pages":[{"page":1,"header":[...],"footer":[...]}, ...]}
"""

from typing import Dict, Any, List, Tuple, Optional
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine
import re

def _normalize_text(s: str) -> str:
    # 공백/줄바꿈 정리
    s = s.replace('\u00A0', ' ')  # nbsp → space
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\s*\n\s*', ' ', s).strip()
    return s

def _top_bottom_lines(layout_objects) -> Tuple[Optional[Tuple[float, float, str]], Optional[Tuple[float, float, str]]]:
    """
    페이지 단위 layout_objects에서 모든 텍스트 라인 추출 후
    - top_line: y1(라인 top)이 가장 큰 라인
    - bottom_line: y0(라인 bottom)이 가장 작은 라인
    반환형: (top_line(y0,y1,text) | None, bottom_line | None)
    """
    lines: List[Tuple[float, float, str]] = []

    for obj in layout_objects:
        if isinstance(obj, LTTextContainer):
            for line in obj:
                if isinstance(line, LTTextLine):
                    txt = _normalize_text(line.get_text() or "")
                    if not txt:
                        continue
                    y0, y1 = line.y0, line.y1
                    lines.append((y0, y1, txt))

    if not lines:
        return None, None

    # header = 가장 위(최대 y1), footer = 가장 아래(최소 y0)
    top_line = max(lines, key=lambda t: t[1])    # max y1
    bot_line = min(lines, key=lambda t: t[0])    # min y0
    return top_line, bot_line

def parse_pdf(file_like) -> Dict[str, Any]:
    """
    외부 호출용 고정 시그니처 (함수명 유지).
    file_like: Django UploadedFile 또는 파일객체
    """
    # pdfminer는 파일 경로/객체 둘 다 가능. 여기서는 file-like 바이트스트림을 그대로 사용
    pages_out: List[Dict[str, Any]] = []
    page_index = 0

    for layout in extract_pages(file_like):
        page_index += 1
        top, bot = _top_bottom_lines(layout)
        header_list = [top[2]] if top else []
        footer_list = [bot[2]] if bot else []
        pages_out.append({
            "page": page_index,
            "header": header_list,
            "footer": footer_list,
        })

    return {
        "v": "1",
        "total_pages": page_index,
        "pages": pages_out
    }
