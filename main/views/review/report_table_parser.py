# -*- coding: utf-8 -*-
"""
report_table_parser.py
- Parse Word tables directly from word/document.xml (flat WordprocessingML).
- Keeps OMML in cell text (inline converted by math parser).

Exports:
  - parse_tables_from_document_xml(xml_bytes) -> List[{"index", "cells"}]
  - parse_table_element(tbl_el) -> {"cells": [...]}

Each cell: [row, col, rowspan, colspan, "text"]  (1-indexed)
"""

from typing import List, Dict, Any
from lxml import etree
from .report_math_parser import parse_omml_to_latex_like

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}

def _serialize(el) -> str:
    return etree.tostring(el, encoding="unicode", with_tail=False)

def _extract_para_with_math(p) -> str:
    """Paragraph → one-line string (math-aware). Avoid parent-level ./w:t duplication."""
    out, skip = [], set()
    for el in p.iter():
        if el in skip:
            continue
        local = el.tag.rsplit('}', 1)[-1] if isinstance(el.tag, str) else ''
        if local in ('oMath', 'oMathPara'):
            out.append(parse_omml_to_latex_like(_serialize(el)))
            for sub in el.iter():
                skip.add(sub)  # prevent collecting w:t inside math twice
            continue
        if local == 't':
            out.append(el.text or '')
            continue
    return ' '.join(''.join(out).split())

def _cell_text(tc_el) -> str:
    paras = tc_el.findall('.//w:p', namespaces=NS)
    parts = [_extract_para_with_math(p) for p in paras]
    return '\n'.join([t for t in parts if t])

def _int_attr(el, qname: str, default: int = 1) -> int:
    if el is None:
        return default
    val = el.get(qname)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default

def parse_table_element(tbl_el) -> dict:
    """
    Input: lxml Element (w:tbl)
    Output: {"cells": [[row, col, rowspan, colspan, "text"], ...]}
    """
    # estimate column count
    grid = tbl_el.find('./w:tblGrid', namespaces=NS)
    if grid is not None:
        max_cols = len(grid.findall('./w:gridCol', namespaces=NS))
    else:
        max_cols = 0
        for tr in tbl_el.findall('./w:tr', namespaces=NS):
            cc = 0
            for tc in tr.findall('./w:tc', namespaces=NS):
                gridSpan = tc.find('./w:tcPr/w:gridSpan', namespaces=NS)
                span = _int_attr(gridSpan, '{%s}val' % NS['w'], 1)
                cc += span
            if cc > max_cols:
                max_cols = cc

    occupancy = {}  # (r,c) -> origin cell list
    final_cells: List[list] = []
    rows = tbl_el.findall('./w:tr', namespaces=NS)

    for r_idx, tr in enumerate(rows):
        real_c = 0
        for tc in tr.findall('./w:tc', namespaces=NS):
            while (r_idx, real_c) in occupancy and real_c < max_cols:
                real_c += 1
            if real_c >= max_cols:
                break

            gridSpan = tc.find('./w:tcPr/w:gridSpan', namespaces=NS)
            vMerge   = tc.find('./w:tcPr/w:vMerge',   namespaces=NS)
            colspan  = _int_attr(gridSpan, '{%s}val' % NS['w'], 1)
            vmerge_val = vMerge.get('{%s}val' % NS['w']) if vMerge is not None else None

            # vertical merge continue
            if vmerge_val == 'continue' or (vMerge is not None and vmerge_val is None):
                origin = None
                for up in range(r_idx - 1, -1, -1):
                    if (up, real_c) in occupancy:
                        origin = occupancy[(up, real_c)]
                        break
                if origin is not None:
                    origin[2] += 1  # rowspan++
                    for c_off in range(colspan):
                        if real_c + c_off < max_cols:
                            occupancy[(r_idx, real_c + c_off)] = origin
                    real_c += colspan
                    continue

            text = _cell_text(tc)
            cell = [r_idx + 1, real_c + 1, 1, colspan, ' '.join((text or '').split())]
            final_cells.append(cell)
            for c_off in range(colspan):
                if real_c + c_off < max_cols:
                    occupancy[(r_idx, real_c + c_off)] = cell
            real_c += colspan

    return {"cells": final_cells}

def parse_tables_from_document_xml(xml_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Input: word/document.xml bytes
    Output: [{"index": 1, "cells": [...]}, ...]
    """
    root = etree.fromstring(xml_bytes)
    body = root.find('.//w:body', namespaces=NS)
    if body is None:
        return []

    tables_out: List[Dict[str, Any]] = []
    idx = 0
    for node in body:
        if not isinstance(node.tag, str):
            continue
        if node.tag.rsplit('}', 1)[-1] == 'tbl':
            idx += 1
            t = parse_table_element(node)
            tables_out.append({"index": idx, "cells": t["cells"]})
    return tables_out

