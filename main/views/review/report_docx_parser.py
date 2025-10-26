# -*- coding: utf-8 -*-
"""
report_docx_parser.py  (v0.5 schema)
- Top-level: {"v":"0.5","header":{page->text},"footer":{page->text},"content":[...]}
- Pages/total_pages 제거, content는 글로벌 중첩 1회 수행
"""

from __future__ import annotations
import io
import json
import re
import unicodedata
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree

# 로컬 모듈 (같은 폴더)
from .report_math_parser import parse_omml_to_latex_like
from .report_table_parser import parse_table_element

# 헤더/푸터 추출 밴드 (상/하 7%)
HEADER_BAND = 0.07
FOOTER_BAND = 0.07

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}

# ------------------------------
# 텍스트/수식 파싱 보조 함수
# ------------------------------
def _extract_para_with_math(p: etree._Element) -> str:
    """
    단락(p)에서 텍스트와 OMML 수식을 섞어 추출.
    """
    out: List[str] = []
    skip: set = set()

    for el in p.iter():
        if el in skip:
            continue
        local = el.tag.rsplit('}', 1)[-1] if isinstance(el.tag, str) else ''
        if local in ("oMath", "oMathPara"):
            latex = parse_omml_to_latex_like(el)
            out.append(latex)
            for sub in el.iter():
                skip.add(sub)
            continue
        if local == "t":  # w:t
            out.append(el.text or '')

    text = ''.join(out)
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _table_anchors(cells: List[List[Any]]) -> Tuple[str, str]:
    """
    표에서 강/약 앵커 추출:
    - strong: 첫 번째 '비어있지 않은 전체 행'의 텍스트(헤더 유사)
    - weak  : 첫 비어있지 않은 행의 첫 셀 텍스트
    """
    by_row: Dict[int, List[Tuple[int, str]]] = {}
    for r, c, rs, cs, txt in cells:
        by_row.setdefault(r, []).append((c, (txt or '').strip()))
    strong, weak = '', ''
    for r in sorted(by_row.keys()):
        row_cells = sorted(by_row[r], key=lambda x: x[0])
        row_text = ' '.join(t for _, t in row_cells if t)
        if row_text and not strong:
            strong = row_text[:120]
        if row_cells and not weak:
            weak = row_cells[0][1][:80]
        if strong and weak:
            break
    return strong, weak


def make_para_anchor(text: str) -> str:
    """
    문단/라벨에서 페이지 매칭에 쓸 짧은 앵커 생성
    """
    text = (text or '').strip()
    # 섹션 라벨 패턴 (1., 1.1, Ⅰ., 가., A., [1] 등)
    m = re.match(r'^\s*(\(?[0-9IVXivx가-하A-Za-z]+(?:\.[0-9]+)*[\.\)]?)\s+', text)
    if m:
        return m.group(1)
    return (text[:50] + '...') if len(text) > 50 else text


# ------------------------------
# PDF에서 헤더/푸터 텍스트 추출
# ------------------------------
def extract_pdf_pages(pdf_path: str):
    """
    pdfplumber를 사용해 상/하 7% 박스에서 텍스트를 추출해
    페이지별 header/footer 라인과 전체 페이지 텍스트를 반환.
    """
    try:
        import pdfplumber
    except Exception:
        # pdfplumber가 없으면 1페이지 빈값으로 진행
        return [{"page": 1, "header": [], "footer": [], "content": []}], [""]

    pages, page_texts = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            w, h = p.width, p.height
            head_box = (0, 0, w, h * HEADER_BAND)
            foot_box = (0, h * (1.0 - FOOTER_BAND), w, h)
            # header
            try:
                htext = p.within_bbox(head_box).extract_text() or ''
                header_lines = [re.sub(r'\s+', ' ', x).strip() for x in htext.split('\n') if x.strip()]
            except Exception:
                header_lines = []
            # footer
            try:
                ftext = p.within_bbox(foot_box).extract_text() or ''
                footer_lines = [re.sub(r'\s+', ' ', x).strip() for x in ftext.split('\n') if x.strip()]
            except Exception:
                footer_lines = []
            pages.append({"page": i, "header": header_lines, "footer": footer_lines, "content": []})
            # page text
            try:
                t = p.extract_text() or ''
            except Exception:
                t = ''
            page_texts.append(re.sub(r'\s+', ' ', t).strip())
    return pages, page_texts


# ------------------------------
# 페이지 매핑/중첩
# ------------------------------
def find_page_for(anchor: str, start_idx: int, page_texts: List[str]) -> int:
    """
    앵커 문자열이 등장하는 페이지를 start_idx부터 탐색하여 반환.
    """
    if not anchor:
        return max(0, start_idx)
    needle = re.escape(anchor[:80])
    for i in range(max(0, start_idx), len(page_texts)):
        if re.search(needle, page_texts[i]):
            return i
    return max(0, start_idx)


def nest_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    라벨/문장/표를 논리 트리로 중첩.
    - 라벨 등장 시 계층 이동, sen/table은 현재 노드의 content에 삽입
    """
    stack: List[Dict[str, Any]] = [{"content": []}]  # root

    def depth_of(label: str) -> int:
        if re.match(r'^\(?[0-9]+(\.[0-9]+)*[\.\)]?$', label):  # 1., 1.1, 2.3.4
            return label.count('.') + 1
        if re.match(r'^[IVXivx]+[\.\)]?$', label):             # Ⅰ., Ⅱ.
            return 1
        if re.match(r'^[가-하]\.?$', label):                   # 가., 나.
            return 2
        if re.match(r'^[A-Za-z]\.?$', label):                  # A., B.
            return 1
        return 1

    for b in blocks:
        kind = b.get('_kind')
        if kind == 'label':
            d = max(1, depth_of(b.get('label', '')))
            # 스택을 d-1까지 유지
            while len(stack) > d:
                stack.pop()
            if len(stack) < d:
                node = {"label": b.get('label', ''), "content": []}
                stack[-1]["content"].append(node)
                stack.append(node)
            else:
                # 동일 레벨 새 라벨
                stack.pop()
                node = {"label": b.get('label', ''), "content": []}
                stack[-1]["content"].append(node)
                stack.append(node)
        elif kind == 'sen':
            stack[-1]["content"].append({"sen": b.get('sen', '')})
        elif kind == 'table':
            stack[-1]["content"].append({"table": b.get('table', [])})
        # 임시 키(_kind/_hint/_anchor/_weak 등)는 최종 반환 전 통으로 버림(여기선 그대로 둬도 무해)

    return stack[0]["content"]


# ------------------------------
# 메인 엔트리
# ------------------------------
def build_pages(docx_path: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
    """
    DOCX 본문을 파싱하여 글로벌 트리를 만들고,
    (옵션) PDF에서 헤더/푸터를 추출해 최상단 dict로 반환.
    """
    # DOCX XML 로드
    with zipfile.ZipFile(docx_path, 'r') as zf:
        doc_xml = zf.read('word/document.xml')
    tree = etree.parse(io.BytesIO(doc_xml))
    root = tree.getroot()
    body = root.find('.//w:body', namespaces=NS)

    # PDF 페이지 정보
    if pdf_path:
        pages, page_texts = extract_pdf_pages(pdf_path)
    else:
        pages, page_texts = [{"page": 1, "header": [], "footer": [], "content": []}], [""]

    total_pages = len(pages)

    # --- 플랫 블록 생성 ---
    flat: List[Dict[str, Any]] = []
    doc_hint = 0  # lastRenderedPageBreak/sectPr nextPage를 만나면 +1

    def add_para_block(text: str, hint_page: int) -> None:
        # 라벨 + 본문 분리 (예: "1. 개요 내용...")
        m = re.match(r'^\s*(\(?[0-9IVXivx가-하A-Za-z]+(?:\.[0-9]+)*[\.\)]?)\s+(.*)$', text)
        if m:
            label_str = m.group(1).strip()
            remainder = (m.group(2) or '').strip()
            anchor = make_para_anchor(label_str) or make_para_anchor(text)
            flat.append({
                "_kind": "label",
                "label": label_str,
                "_anchor": anchor,
                "_hint": hint_page
            })
            if remainder:
                flat.append({
                    "_kind": "sen",
                    "sen": remainder,
                    "_anchor": make_para_anchor(remainder),
                    "_hint": hint_page
                })
        else:
            flat.append({
                "_kind": "sen",
                "sen": text,
                "_anchor": make_para_anchor(text),
                "_hint": hint_page
            })

    if body is not None:
        for node in body:
            if not isinstance(node.tag, str):
                continue
            local = node.tag.rsplit('}', 1)[-1]

            if local == 'p':
                # 페이지 나누기 마커(lastRenderedPageBreak) → 힌트 증가
                if node.findall('.//w:lastRenderedPageBreak', namespaces=NS):
                    doc_hint += 1
                text = _extract_para_with_math(node).strip()
                if text:
                    add_para_block(text, doc_hint)

                # sectPr nextPage도 페이지 힌트 증가
                sect_type = node.find('.//w:sectPr/w:type', namespaces=NS)
                if sect_type is not None and sect_type.get(f'{{{NS["w"]}}}val') == 'nextPage':
                    doc_hint += 1

            elif local == 'tbl':
                tdict = parse_table_element(node)  # {"cells":[[r,c,rs,cs,"text"], ...]}
                strong, weak = _table_anchors(tdict["cells"])
                flat.append({
                    "_kind": "table",
                    "table": tdict["cells"],
                    "_anchor": strong,
                    "_weak": weak,
                    "_hint": doc_hint
                })
                # 표 뒤에 섹션 나눔이 따르는 경우를 대비
                sect_type = node.find('.//w:sectPr/w:type', namespaces=NS)
                if sect_type is not None and sect_type.get(f'{{{NS["w"]}}}val') == 'nextPage':
                    doc_hint += 1

    # --- 1차 페이지 매핑(힌트+앵커) ---
    page_buckets: List[List[Optional[Dict[str, Any]]]] = [[] for _ in range(total_pages)]
    current_page = 0
    for b in flat:
        start = min(max(b.get('_hint', current_page), 0), total_pages - 1)
        page_idx = find_page_for(b.get('_anchor') or '', start, page_texts)
        page_buckets[page_idx].append(b)
        current_page = max(current_page, page_idx)

    # --- (선택) 표 충돌 간단 분배: 같은 weak 헤더 다중 연속 시 앞쪽 페이지로 분산 ---
    # 복잡한 재분배는 생략(필요 시 후속 개선), None 마킹 없이 그대로 사용

    # --- 최상단 header/footer dict 구성 ---
    header_map: Dict[str, str] = {
        str(pg.get("page", i + 1)): "\n".join(pg.get("header", []))
        for i, pg in enumerate(pages)
    }
    footer_map: Dict[str, str] = {
        str(pg.get("page", i + 1)): "\n".join(pg.get("footer", []))
        for i, pg in enumerate(pages)
    }

    # --- 글로벌 중첩: 모든 페이지 블록을 합쳐 1회 nest_blocks() ---
    all_blocks: List[Dict[str, Any]] = []
    for i in range(total_pages):
        for b in page_buckets[i]:
            if b is not None:
                all_blocks.append(b)

    content = nest_blocks(all_blocks)

    return {
        "v": "0.5",
        "header": header_map,
        "footer": footer_map,
        "content": content,
    }


# CLI 테스트용
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", help="input .docx path")
    parser.add_argument("--pdf", help="optional pdf path for header/footer extraction")
    parser.add_argument("--out", help="write JSON to file (UTF-8 BOM)")
    args = parser.parse_args()

    data = build_pages(args.docx, pdf_path=args.pdf)
    if args.out:
        with open(args.out, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
