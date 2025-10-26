# -*- coding: utf-8 -*-
from typing import Dict, Any, List, Tuple, Optional
from io import BytesIO
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTTextLine
import re

def _normalize_text(s: str) -> str:
    s = s.replace('\u00A0', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\s*\n\s*', ' ', s).strip()
    return s

def _top_bottom_lines(layout_objects) -> Tuple[Optional[Tuple[float, float, str]], Optional[Tuple[float, float, str]]]:
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
    top_line = max(lines, key=lambda t: t[1])  # header = 가장 위(최대 y1)
    bot_line = min(lines, key=lambda t: t[0])  # footer = 가장 아래(최소 y0)
    return top_line, bot_line

def parse_pdf(file_like) -> Dict[str, Any]:
    """
    외부 시그니처 유지: Django InMemoryUploadedFile 등 file-like 객체를 받아 처리.
    내부에서 bytes로 읽어 BytesIO로 감싸 pdfminer에 전달한다.
    """
    # file-like → bytes → BytesIO 로 표준화
    try:
        if hasattr(file_like, "seek"):
            file_like.seek(0)
        data = file_like.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        bio = BytesIO(data)
        bio.seek(0)
    except Exception as e:
        raise RuntimeError(f"Failed to read PDF bytes: {e}")

    pages_out: List[Dict[str, Any]] = []
    page_index = 0

    # extract_pages는 파일 경로나 바이너리 스트림(파일 객체)을 받는다 → BytesIO 사용
    for layout in extract_pages(bio):
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
