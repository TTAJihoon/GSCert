# -*- coding: utf-8 -*-
"""
report_docx_parser.py (fixed v2.2)
- Robust redistribution loop (no stray 'continue')
- Disambiguate repeated tables with same header across pages
"""

import io, json, sys, zipfile, re, unicodedata
from typing import List, Dict, Any, Optional, Tuple
from lxml import etree

from .report_math_parser import parse_omml_to_latex_like
from .report_table_parser import parse_table_element

HEADER_BAND = 0.07
FOOTER_BAND = 0.07
...
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}

def _serialize(el) -> str:
    return etree.tostring(el, encoding='unicode', with_tail=False)

def _extract_para_with_math(p) -> str:
    out, skip = [], set()
    for el in p.iter():
        if el in skip:
            continue
        local = el.tag.rsplit('}', 1)[-1] if isinstance(el.tag, str) else ''
        if local == 'oMath' or local == 'oMathPara':
            # OMML 수식 -> 라텍스 유사 문자열
            latex = parse_omml_to_latex_like(el)
            out.append(latex)
            for sub in el.iter():
                skip.add(sub)
            continue
        if local == 't':  # w:t
            out.append(el.text or '')
    text = ''.join(out)
    # 한글/영문 공백 정리
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def _table_anchors(cells: List[List[Any]]) -> Tuple[str, str]:
    """
    strong anchor: first non-empty full-row text (header-ish)
    weak  anchor: first cell of first non-empty row
    """
    by_row: Dict[int, List[str]] = {}
    for r, c, rs, cs, txt in cells:
        by_row.setdefault(r, []).append((c, txt.strip()))
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
    text = text.strip()
    # 섹션 라벨 패턴 (예: "1.", "2.1", "Ⅲ.", "가.", "A.", "[1]" 등)
    m = re.match(r'^\s*(\(?[0-9IVXivx가-하A-Za-z]+[\.\)]?)\s+', text)
    if m:
        return m.group(1)
    # 일반 문장 앵커
    return (text[:50] + '...') if len(text) > 50 else text

def extract_pdf_pages(pdf_path: str):
    """
    pdfplumber 사용 가정: 상/하 7% 밴드에서 header/footer 텍스트 추출,
    전체 텍스트도 페이지별로 확보 (앵커 매칭에 사용)
    """
    try:
        import pdfplumber
    except Exception:
        # pdfplumber 없으면 헤더/푸터 빈값으로라도 진행
        return [{"page": 1, "header": [], "footer": [], "content": []}], [""]

    pages, page_texts = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            w, h = p.width, p.height
            head_box = (0, 0, w, h * HEADER_BAND)
            foot_box = (0, h * (1.0 - FOOTER_BAND), w, h)
            header_lines, footer_lines = [], []
            try:
                header_lines = [re.sub(r'\s+', ' ', x).strip()
                                for x in (p.within_bbox(head_box).extract_text() or '').split('\n')
                                if x.strip()]
            except Exception:
                header_lines = []
            try:
                footer_lines = [re.sub(r'\s+', ' ', x).strip()
                                for x in (p.within_bbox(foot_box).extract_text() or '').split('\n')
                                if x.strip()]
            except Exception:
                footer_lines = []
            pages.append({"page": i, "header": header_lines, "footer": footer_lines, "content": []})
            try:
                t = p.extract_text() or ''
            except Exception:
                t = ''
            page_texts.append(re.sub(r'\s+', ' ', t).strip())
    return pages, page_texts

def find_page_for(anchor: str, start_idx: int, page_texts: List[str]) -> int:
    """
    앵커 문자열이 가장 먼저(혹은 start_idx 이후) 등장하는 페이지를 찾는다.
    """
    if not anchor:
        return start_idx
    needle = re.escape(anchor[:80])
    for i in range(max(0, start_idx), len(page_texts)):
        if re.search(needle, page_texts[i]):
            return i
    # fallback: 이전 페이지에도 없으면 start_idx 그대로
    return start_idx

def nest_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    라벨/문장/표를 논리 트리로 중첩.
    - label이 계층을 올리고, sen/table은 현재 스택의 맨 아래 content에 삽입
    - depth는 라벨 문자열 패턴에서 추정
    """
    stack: List[Dict[str, Any]] = [{"content": []}]  # root
    def depth_of(label: str) -> int:
        # 숫자/로마자/한글계층 단순 추정
        if re.match(r'^\(?[0-9]+(\.[0-9]+)*[\.\)]?$', label):      # 1., 1.1, 2.3.4
            return label.count('.') + 1
        if re.match(r'^[IVXivx]+[\.\)]?$', label):                 # Ⅰ., Ⅱ.
            return 1
        if re.match(r'^[가-하]\.?$', label):                       # 가., 나.
            return 2
        if re.match(r'^[A-Za-z]\.?$', label):                      # A., B.
            return 1
        return 1

    for b in blocks:
        kind = b.get('_kind')
        if kind == 'label':
            d = max(1, depth_of(b.get('label', '')))
            while len(stack) > d:
                stack.pop()
            if len(stack) < d:
                # 새 노드 삽입
                node = {"label": b.get('label', ''), "content": []}
                stack[-1]["content"].append(node)
                stack.append(node)
            else:
                # 동일 레벨 새 라벨
                node = {"label": b.get('label', ''), "content": []}
                stack.pop()
                stack[-1]["content"].append(node)
                stack.append(node)
        elif kind == 'sen':
            stack[-1]["content"].append({"sen": b.get('sen', '')})
        elif kind == 'table':
            stack[-1]["content"].append({"table": b.get('table', [])})
        # 임시키 제거는 여기서 하지 않고, 최종 반환 전에 일괄 제거 가능
    # root content 반환
    return stack[0]["content"]

def build_pages(docx_path: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
    # Load DOCX XML
    with zipfile.ZipFile(docx_path, 'r') as z:
        doc_xml = z.read('word/document.xml')
    tree = etree.parse(io.BytesIO(doc_xml))
    root = tree.getroot()
    body = root.find('.//w:body', namespaces=NS)

    # PDF pages
    if pdf_path:
        pages, page_texts = extract_pdf_pages(pdf_path)
    else:
        pages, page_texts = [{"page": 1, "header": [], "footer": [], "content": []}], [""]
    total_pages = len(pages)

    # Flatten
...
            anchor = make_para_anchor(label_str) or make_para_anchor(text)
            flat.append({"_kind":"label","label":label_str,"depth":depth,"_anchor": anchor, "_hint": hint_page})
            if remainder:
                flat.append({"_kind":"sen","sen":remainder,"_anchor": make_para_anchor(remainder), "_hint": hint_page})
        else:
            flat.append({"_kind":"sen","sen":text,"_anchor": make_para_anchor(text), "_hint": hint_page})

    if body is not None:
        for node in body:
            if not isinstance(node.tag, str):
                continue
            local = node.tag.rsplit('}',1)[-1]
            if local == 'p':
                if node.findall('.//w:lastRenderedPageBreak', namespaces=NS):
                   
                doc_hint += 1
                text = _extract_para_with_math(node).strip()
                if text:
                    add_para_block(text, doc_hint)
            elif local == 'tbl':
                tdict = parse_table_element(node)
                strong, weak = _table_anchors(tdict["cells"])
                flat.append({"_kind":"table","table": tdict["cells"], "_anchor": strong, "_weak": weak, "_hint": doc_hint})
            sect = node.find('.//w:sectPr/w:type', namespaces=NS)
            if sect is not None and sect.get('{%s}val' % NS['w']) == 'nextPage':
                doc_hint += 1

    # First pass mapping
    page_buckets = [[] for _ in range(total_pages)]
    current_page = 0
    for b in flat:
        start = min(max(b.get('_hint', current_page), 0), total_pages-1)
        page_idx = find_page_for(b.get('_anchor') or "", start, page_texts)
        page_buckets[page_idx].append(b)
        current_page = max(current_page, page_idx)

    # Redistribution: group same weak-header tables that collided on one page
    def pages_with_token(token: str) -> List[int]:
  
            weak = blk.get('_weak', '')
            # collect consecutive tables with same weak header
            run_idx = [j]
            k = j + 1
            while k < len(page_buckets[i]):
                b2 = page_buckets[i][k]
                if b2.get('_kind') == 'table' and b2.get('_weak', '') == weak:
                    run_idx.append(k)
                    k += 1
                else:
                    break
            if len(run_idx) >= 2 and weak:
                moved_any = False
                target_pages = [p for p in pages_with_token(weak) if p >= i]
                if len(target_pages) >= 2:
                    # distribute to listed target pages first
                    for offset, idx_in_bucket in enumerate(run_idx[1:], start=1):
                        dest = target_pages[min(offset, len(target_pages)-1)]
                        if dest != i:
                            tb = page_buckets[i][idx_in_bucket]
                            page_buckets[dest].append(tb)
                            page_buckets[i][idx_in_bucket] = None
                            moved_any = True
                # fallback: sequential forward pages
                if not moved_any:
                    for offset, idx_in_bucket in enumerate(run_idx[1:], start=1):
                        dest = min(i + offset, total_pages - 1)
                        if dest != i:
                            tb = page_buckets[i][idx_in_bucket]
                            page_buckets[dest].append(tb)
...
    # ---- 여기부터 v0.5 스키마 반환 ----
    # Build header/footer maps at top-level (page -> text)
    header_map = {str(pg.get("page", i+1)): "\n".join(pg.get("header", [])) for i, pg in enumerate(pages)}
    footer_map = {str(pg.get("page", i+1)): "\n".join(pg.get("footer", [])) for i, pg in enumerate(pages)}

    # Global nesting: flatten all page buckets and nest once for the entire document
    all_blocks = []
    for i in range(total_pages):
        for b in page_buckets[i]:
            if b is not None:
                all_blocks.append(b)
    content = nest_blocks(all_blocks)

    return {"v": "0.5", "header": header_map, "footer": footer_map, "content": content}
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("docx")
    parser.add_argument("--pdf")
    parser.add_argument("--out", help="write JSON to file (UTF-8 BOM)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    data = build_pages(args.docx, pdf_path=args.pdf)

    if args.out:
        with open(args.out, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
