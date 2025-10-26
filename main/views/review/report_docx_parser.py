# -*- coding: utf-8 -*-
from __future__ import annotations
import io
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import List, Dict, Any

W_NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
M_NS = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}

WVAL = ET.QName(W_NS['w'], 'val')
WCHAR = ET.QName(W_NS['w'], 'char')

def _omml_text(el: ET.Element) -> str:
    local = el.tag.split('}', 1)[-1]
    if local in ('oMathPara', 'oMath'):
        return ''.join(_omml_text(ch) for ch in list(el))
    if local == 'r':
        out = []
        t = el.find('m:t', M_NS)
        if t is not None and t.text:
            out.append(t.text)
        for t2 in el.findall('w:t', W_NS):
            if t2.text:
                out.append(t2.text)
        for inner in el.findall('m:oMath', M_NS):
            out.append(_omml_text(inner))
        return ''.join(out)
    if local == 'nary':
        chr_el = el.find('m:naryPr/m:chr', M_NS)
        op = '∑'
        if chr_el is not None:
            v = chr_el.get(ET.QName(M_NS['m'], 'val'))
            if v:
                try:
                    op = chr(int(v, 16))
                except Exception:
                    pass
        sub_txt = _omml_text(el.find('m:sub', M_NS)) or ''
        sup_txt = _omml_text(el.find('m:sup', M_NS)) or ''
        body    = _omml_text(el.find('m:e',   M_NS)) or ''
        limiter = ''
        if sub_txt and sup_txt:
            limiter = f"_{{{sub_txt}}}^{{{sup_txt}}}"
        elif sub_txt:
            limiter = f"_{{{sub_txt}}}"
        elif sup_txt:
            limiter = f"^{{{sup_txt}}}"
        return f"{op}{limiter}({body})"
    if local == 'f':
        num = _omml_text(el.find('m:num', M_NS)) or ''
        den = _omml_text(el.find('m:den', M_NS)) or ''
        return f"({num})/({den})"
    if local == 'sSup':
        base = _omml_text(el.find('m:e',   M_NS)) or ''
        sup  = _omml_text(el.find('m:sup', M_NS)) or ''
        return f"{base}^{sup}" if sup else base
    if local == 'sSub':
        base = _omml_text(el.find('m:e',   M_NS)) or ''
        sub  = _omml_text(el.find('m:sub', M_NS)) or ''
        return f"{base}_{sub}" if sub else base
    if local == 'sSubSup':
        base = _omml_text(el.find('m:e',   M_NS)) or ''
        sub  = _omml_text(el.find('m:sub', M_NS)) or ''
        sup  = _omml_text(el.find('m:sup', M_NS)) or ''
        if sub and sup:
            return f"{base}_{sub}^{sup}"
        if sub:
            return f"{base}_{sub}"
        if sup:
            return f"{base}^{sup}"
        return base
    if local == 'd':
        beg = el.find('m:dPr/m:begChr', M_NS)
        end = el.find('m:dPr/m:endChr', M_NS)
        begc = beg.get(ET.QName(M_NS['m'], 'val')) if beg is not None else '('
        endc = end.get(ET.QName(M_NS['m'], 'val')) if end is not None else ')'
        inner = ''.join(_omml_text(c) for c in el.findall('m:e', M_NS))
        return f"{begc}{inner}{endc}"
    return ''.join(t.text or '' for t in el.findall('.//w:t', W_NS))

def _run_text_with_math(r: ET.Element) -> str:
    out = []
    sym = r.find('w:sym', W_NS)
    if sym is not None:
        ch = sym.get(WCHAR)
        if ch:
            try:
                out.append(chr(int(ch, 16)))
            except Exception:
                pass
    for t in r.findall('w:t', W_NS):
        if t.text:
            out.append(t.text)
    for m in r.findall('m:oMath', M_NS):
        out.append(_omml_text(m))
    return ''.join(out)

def _paragraph_text(p: ET.Element) -> str:
    s = []
    for r in p.findall('w:r', W_NS):
        s.append(_run_text_with_math(r))
    for m in p.findall('m:oMath', M_NS):
        s.append(_omml_text(m))
    for mp in p.findall('m:oMathPara', M_NS):
        s.append(_omml_text(mp))
    return ''.join(s).strip()

def _cell_text(tc: ET.Element) -> str:
    lines = [_paragraph_text(p) for p in tc.findall('.//w:p', W_NS)]
    for m in tc.findall('.//m:oMath', M_NS):
        txt = _omml_text(m)
        if txt:
            lines.append(txt)
    lines = [ln for ln in lines if ln]
    return '\n'.join(lines)

def _parse_table(tbl: ET.Element) -> Dict[str, Any]:
    out: List[List[Any]] = []
    from collections import defaultdict
    rowspans = defaultdict(int)   # out_idx -> rowspan 누적
    active_v = {}                 # col_idx -> 시작셀 out_idx
    row_idx = 0
    for tr in tbl.findall('w:tr', W_NS):
        row_idx += 1
        col_idx = 1
        for tc in tr.findall('w:tc', W_NS):
            tcPr = tc.find('w:tcPr', W_NS)
            gridSpan = 1
            vMerge = None
            if tcPr is not None:
                g = tcPr.find('w:gridSpan', W_NS)
                if g is not None and g.get(WVAL):
                    try:
                        gridSpan = int(g.get(WVAL))
                    except Exception:
                        gridSpan = 1
                vMerge = tcPr.find('w:vMerge', W_NS)
            text = (_cell_text(tc) or '').strip()
            vm_val = vMerge.get(WVAL) if vMerge is not None else None
            is_continue = (vMerge is not None) and (vm_val is None or vm_val == 'continue')
            is_restart  = (vMerge is not None) and (vm_val and vm_val != 'continue')
            if is_continue:
                start_idx = active_v.get(col_idx)
                if start_idx is not None:
                    rowspans[start_idx] += 1
            else:
                entry = [row_idx, col_idx, 1, gridSpan, text]
                out_idx = len(out)
                out.append(entry)
                rowspans[out_idx] += 1
                if is_restart:
                    active_v[col_idx] = out_idx
            col_idx += gridSpan
    for i, entry in enumerate(out):
        entry[2] = rowspans[i]
    return {"table": out}

def parse_docx_to_json(docx_file, with_paragraphs: bool = True) -> Dict[str, Any]:
    if isinstance(docx_file, str):
        with open(docx_file, 'rb') as f:
            data = f.read()
    elif isinstance(docx_file, (bytes, bytearray)):
        data = bytes(docx_file)
    elif hasattr(docx_file, 'read'):
        data = docx_file.read()
    else:
        raise TypeError("DOCX path/file/bytes only.")
    with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
        xml = zf.read('word/document.xml')
    root = ET.fromstring(xml)
    body = root.find('.//w:body', W_NS)
    content: List[Dict[str, Any]] = []
    if body is None:
        return {"v": "1", "docx": {"v": "1", "content": content}}
    for child in list(body):
        tag = child.tag.split('}', 1)[-1]
        if tag == 'tbl':
            content.append(_parse_table(child))
        elif tag == 'p' and with_paragraphs:
            txt = _paragraph_text(child)
            if txt:
                content.append({"sen": txt})
    return {"v": "1", "docx": {"v": "1", "content": content}}
