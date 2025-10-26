# -*- coding: utf-8 -*-
"""
report_docx_parser.py (fixed v2.2)
- Robust redistribution loop (no stray 'continue')
- Disambiguate repeated tables with same header across pages
"""

import io, json, sys, zipfile, re, unicodedata
from typing import List, Dict, Any, Optional, Tuple
from lxml import etree

try:
    from report_math_parser import parse_omml_to_latex_like as parse_omml_to_text
except ImportError:
    from report_math_parser import parse_omml_to_text

from report_table_parser import parse_table_element

HEADER_BAND = 0.07
FOOTER_BAND = 0.07
ANCHOR_MAXLEN = 120
ANCHOR_MINLEN = 16
SEARCH_WINDOW = 2
INDEX_BODY_ONLY = True

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
        if local in ('oMath', 'oMathPara'):
            out.append(parse_omml_to_text(_serialize(el)))
            for sub in el.iter():
                skip.add(sub)
            continue
        if local == 't':
            out.append(el.text or '')
            continue
    return ' '.join(''.join(out).split())

def read_part_from_docx(docx_path: str, part: str) -> bytes:
    with zipfile.ZipFile(docx_path, 'r') as z:
        return z.read(part)

NUM_LABEL_RE = re.compile(r'^(?P<num>(?:\d+\.)+)\s+(?P<title>.+?)\s*$')
NUM_LABEL_RE_LOOSE = re.compile(r'^(?P<num>\d+(?:\.\d+)*)\s+(?P<title>[^\d].+?)\s*$')
VERSION_LIKE_RE = re.compile(r'^[vV]\d+(?:\.\d+){1,3}\b')
BRACKET_LABEL_RE = re.compile(r'^\s*<\s*([^>]+?)\s*>\s*(.*)$')

def is_version_like(s: str) -> bool:
    return bool(VERSION_LIKE_RE.match(s.strip()))

def _ensure_display_num(num: str) -> str:
    if num.endswith('.'):
        return num
    if '.' in num:
        return num
    return num + '.'

def detect_label(text: str) -> Optional[Tuple[str, int, str]]:
    s = text.strip()
    if not s:
        return None
    m = NUM_LABEL_RE.match(s)
    if m and not is_version_like(s):
        num = m.group('num')
        title = m.group('title')
        depth = len([x for x in num.split('.') if x])
        num_clean = num[:-1] if num.endswith('.') else num
        disp = f"{_ensure_display_num(num_clean)} {title}"
        return (disp, depth, "")
    m2 = NUM_LABEL_RE_LOOSE.match(s)
    if m2 and not is_version_like(s):
        num = m2.group('num')
        title = m2.group('title')
        depth = len(num.split('.'))
        disp = f"{_ensure_display_num(num)} {title}"
        return (disp, depth, "")
    b = BRACKET_LABEL_RE.match(s)
    if b:
        label_text = b.group(1).strip()
        remainder = b.group(2).strip()
        return (f"<{label_text}>", 1, remainder)
    return None

def normalize_for_anchor(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize('NFC', s)
    s = s.replace('\n', ' ')
    s = re.sub(r'\s+', ' ', s)
    s = s.strip().casefold()
    s = re.sub(r'[\u200b-\u200f]', '', s)
    s = re.sub(r'[·•∙ㆍ]+', '·', s)
    return s

def shorten_anchor(s: str, maxlen: int = ANCHOR_MAXLEN) -> str:
    s = normalize_for_anchor(s)
    return s[:maxlen]

def good_anchor(s: str) -> bool:
    return len(s) >= ANCHOR_MINLEN

def extract_pdf_pages(pdf_path: str):
    pages, page_texts = [], []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for i, p in enumerate(pdf.pages, 1):
                w, h = p.width, p.height
                top = p.within_bbox((0, 0, w, HEADER_BAND * h))
                bot = p.within_bbox((0, (1.0 - FOOTER_BAND) * h, w, h))
                header_lines = [t.strip() for t in (top.extract_text() or '').splitlines() if t.strip()]
                footer_lines = [t.strip() for t in (bot.extract_text() or '').splitlines() if t.strip()]
                pages.append({"page": i, "header": header_lines, "footer": footer_lines, "content": []})
                mid = p.within_bbox((0, HEADER_BAND * h, w, (1.0 - FOOTER_BAND) * h)) if INDEX_BODY_ONLY else p
                txt = mid.extract_text() or ""
                page_texts.append(normalize_for_anchor(txt))
    except Exception:
        pages = [{"page": 1, "header": [], "footer": [], "content": []}]
        page_texts = [""]
    return pages, page_texts

def make_para_anchor(text: str) -> str:
    s = shorten_anchor(text)
    return s if good_anchor(s) else ""

def _table_anchors(cells: List[List[Any]]) -> Tuple[str, str]:
    """Return (strong_anchor, weak_header_anchor)."""
    from collections import defaultdict
    rows = defaultdict(list)
    for r, c, rs, cs, txt in cells:
        rows[r].append(txt or "")

    header = ' '.join([t for t in rows.get(1, []) if t]).strip()
    weak = shorten_anchor(header) if header else ""

    # strong: header + first row2 meaningful text
    row2 = ' '.join([t for t in rows.get(2, []) if t]).strip()
    strong = shorten_anchor(f"{header} {row2}".strip()) if (header or row2) else ""

    # fallback: accumulate up to 8 non-empty cells
    if not good_anchor(strong):
        join, cnt = [], 0
        for _, _, _, _, txt in cells:
            if txt and txt.strip():
                join.append(txt.strip())
                cnt += 1
                if cnt >= 8:
                    break
        strong = shorten_anchor(' '.join(join))

    if not good_anchor(strong):
        strong = ""

    return strong, weak

def nest_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out, stack = [], []
    for b in blocks:
        k = b.get('_kind')
        if k == 'label':
            depth = b['depth']
            while stack and stack[-1]['depth'] >= depth:
                stack.pop()
            node = {"label": b["label"], "content": [], "depth": depth}
            if stack:
                stack[-1]["content"].append(node)
            else:
                out.append(node)
            stack.append(node)
        elif k in ('sen', 'table'):
            node = {k: b[k]}
            if stack:
                stack[-1]["content"].append(node)
            else:
                out.append(node)
    def strip(n):
        if isinstance(n, dict):
            n.pop('depth', None)
            if 'content' in n and isinstance(n['content'], list):
                for ch in n['content']:
                    strip(ch)
    for n in out:
        strip(n)
    return out

def find_page_for(anchor: str, start_page: int, page_texts: List[str]) -> int:
    if not anchor:
        return start_page
    total = len(page_texts)
    def score(page_idx: int) -> tuple[int,int]:
        pos = page_texts[page_idx].find(anchor)
        return (1 if pos >= 0 else 0, -pos if pos >= 0 else -10_000_000)
    order = [start_page] + [start_page + d for d in range(1, SEARCH_WINDOW + 1) if start_page + d < total] \
                        + [start_page - d for d in range(1, SEARCH_WINDOW + 1) if start_page - d >= 0]
    candidates = [(score(p), p) for p in order if anchor in page_texts[p]]
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    global_candidates = [(score(p), p) for p in range(total) if anchor in page_texts[p]]
    if global_candidates:
        global_candidates.sort(reverse=True)
        return global_candidates[0][1]
    return start_page

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
    flat: List[Dict[str, Any]] = []
    doc_hint = 0

    def add_para_block(text: str, hint_page: int):
        det = detect_label(text)
        if det:
            label_str, depth, remainder = det
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
        if not token:
            return []
        return [i for i, txt in enumerate(page_texts) if token in txt]

    for i in range(total_pages):
        j = 0
        while j < len(page_buckets[i]):
            blk = page_buckets[i][j]
            if blk.get('_kind') != 'table':
                j += 1
                continue
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
                            page_buckets[i][idx_in_bucket] = None
                            moved_any = True
                # compact and restart scanning on this page
                page_buckets[i] = [b for b in page_buckets[i] if b is not None]
                j = 0
                continue
            j = k

    # Nest per page
    for i in range(total_pages):
        nested = nest_blocks(page_buckets[i])
        pages[i]["content"] = nested

    return {"v": "0.4", "total_pages": total_pages, "pages": pages}

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
