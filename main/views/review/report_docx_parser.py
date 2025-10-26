# -*- coding: utf-8 -*-
"""
report_docx_parser.py

- DOCX에서 표/문단/수식을 문서 흐름 순서대로 파싱하여 JSON으로 반환
- OMML(∑, 분수, 첨자, 괄호, limLow/limUpp 등) 선형화
- 일반 텍스트 런(w:r)의 vertAlign(sub/sup)도 수식처럼 선형화 (A_{i}, x^{2})
- 표 병합(rowspan/colspan) 정확 반영
- meta 제거
"""

from __future__ import annotations
import io
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import List, Dict, Any, Optional

W_NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
M_NS = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}

WVAL  = ET.QName(W_NS['w'], 'val')
WCHAR = ET.QName(W_NS['w'], 'char')

# =========================
# OMML → 선형 텍스트
# =========================

def _text_all(el: ET.Element, xpath: str, ns: dict) -> str:
    return ''.join((t.text or '') for t in el.findall(xpath, ns))

def _omml_text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ''
    local = el.tag.split('}', 1)[-1]

    # 컨테이너
    if local in ('oMathPara', 'oMath'):
        return ''.join(_omml_text(ch) for ch in list(el))

    # 수식 런
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

    # 대형 연산자(∑ 등)
    if local == 'nary':
        # 연산자
        chr_el = el.find('m:naryPr/m:chr', M_NS)
        op = '∑'
        if chr_el is not None:
            v = chr_el.get(ET.QName(M_NS['m'], 'val'))
            if v:
                try:
                    op = chr(int(v, 16))
                except Exception:
                    pass

        # 하/상한과 본문
        sub_txt = _omml_text(el.find('m:sub', M_NS)) or ''
        sup_txt = _omml_text(el.find('m:sup', M_NS)) or ''

        # 본문은 m:e가 여러 개일 수 있어 모두 결합
        e_nodes = el.findall('m:e', M_NS)
        if e_nodes:
            body = ''.join(_omml_text(n) for n in e_nodes)
        else:
            # 폴백: 내부 모든 텍스트 수집
            body = _text_all(el, './/w:t', W_NS)

        limiter = ''
        if sub_txt and sup_txt:
            limiter = f"_{{{sub_txt}}}^{{{sup_txt}}}"
        elif sub_txt:
            limiter = f"_{{{sub_txt}}}"
        elif sup_txt:
            limiter = f"^{{{sup_txt}}}"

        # 상/하한이 비면 생략
        return f"{op}{limiter}({body})"

    # limLow / limUpp (∑ 이외 일반 개체에 붙는 상하한)
    if local == 'limLow':
        base = _omml_text(el.find('m:e', M_NS))
        low  = _omml_text(el.find('m:lim', M_NS))
        return f"{base}_{{{low}}}" if low else base
    if local == 'limUpp':
        base = _omml_text(el.find('m:e', M_NS))
        upp  = _omml_text(el.find('m:lim', M_NS))
        return f"{base}^{{{upp}}}" if upp else base

    # 분수
    if local == 'f':
        num = _omml_text(el.find('m:num', M_NS))
        den = _omml_text(el.find('m:den', M_NS))
        return f"({num})/({den})"

    # 첨자
    if local == 'sSup':
        base = _omml_text(el.find('m:e',   M_NS))
        sup  = _omml_text(el.find('m:sup', M_NS))
        return f"{base}^{sup}" if sup else base
    if local == 'sSub':
        base = _omml_text(el.find('m:e',   M_NS))
        sub  = _omml_text(el.find('m:sub', M_NS))
        return f"{base}_{sub}" if sub else base
    if local == 'sSubSup':
        base = _omml_text(el.find('m:e',   M_NS))
        sub  = _omml_text(el.find('m:sub', M_NS))
        sup  = _omml_text(el.find('m:sup', M_NS))
        if sub and sup:
            return f"{base}_{sub}^{sup}"
        if sub:
            return f"{base}_{sub}"
        if sup:
            return f"{base}^{sup}"
        return base

    # 델리미터(괄호 등)
    if local == 'd':
        beg = el.find('m:dPr/m:begChr', M_NS)
        end = el.find('m:dPr/m:endChr', M_NS)
        begc = beg.get(ET.QName(M_NS['m'], 'val')) if beg is not None else '('
        endc = end.get(ET.QName(M_NS['m'], 'val')) if end is not None else ')'
        inner = ''.join(_omml_text(c) for c in el.findall('m:e', M_NS))
        return f"{begc}{inner}{endc}"

    # 기타(상자, 오버바 등)는 내부 텍스트만
    return _text_all(el, './/w:t', W_NS)


# =========================
# 일반 텍스트 런 처리(첨자)
# =========================

def _run_text_with_math(r: ET.Element, prev_base: Optional[str]) -> (str, Optional[str]):
    """
    w:r을 선형 텍스트로.
    - w:sym → 문자(∑ 등)
    - w:t → 일반 텍스트
    - m:oMath → OMML
    - w:rPr/w:vertAlign = subscript/superscript → _{...}/^{...}
      - base는 직전 토큰(prev_base)에 붙인다.
    """
    out = []
    rPr = r.find('w:rPr', W_NS)
    vert = rPr.find('w:vertAlign', W_NS) if rPr is not None else None
    vert_val = vert.get(WVAL) if vert is not None else None

    # 수식이 런 안에 직접 있을 수 있음
    math_inside = r.findall('m:oMath', M_NS)
    if math_inside:
        txt = ''.join(_omml_text(m) for m in math_inside)
        out.append(txt)
        return ''.join(out), None

    # 심볼(예: ∑)
    sym = r.find('w:sym', W_NS)
    if sym is not None:
        ch = sym.get(WCHAR)
        if ch:
            try:
                out.append(chr(int(ch, 16)))
                return ''.join(out), out[-1]  # 방금 출력한 문자를 base 후보로
            except Exception:
                pass

    # 일반 텍스트
    t_texts = [t.text for t in r.findall('w:t', W_NS) if t.text]
    raw = ''.join(t_texts)

    if not raw:
        return '', prev_base

    if vert_val in ('subscript', 'superscript'):
        # 첨자인 경우: 직전 base가 있으면 붙이고, 없으면 자체를 base로 간주
        token = raw.strip()
        if not token:
            return '', prev_base

        if prev_base:
            # prev_base를 out에서 제거하고, 결합하여 다시 out에 넣어준다
            base = prev_base
            # out이 비어있으면 base는 직전 문단에서 올 수 있으니 그대로 사용
            # 첨자는 항상 { }로 감쌈 (여러 글자 보호)
            if vert_val == 'subscript':
                combined = f"{base}_{{{token}}}"
            else:
                combined = f"{base}^{{{token}}}"
            # prev_base가 이미 out 끝에 존재할지 확실치 않으므로 그냥 combined만 반환
            return combined, combined  # 결합된 식을 새 base로
        else:
            # base가 없다면 토큰만(다음 런에서 base로 쓸 수 있도록)
            # 표기상 의미가 애매하므로 그냥 토큰 반환
            if vert_val == 'subscript':
                return f"_{{{token}}}", f"_{{{token}}}"
            else:
                return f"^{{{token}}}", f"^{{{token}}}"

    # 일반 텍스트(첨자 아님)
    out.append(raw)
    # 마지막 문자(영숫자/그리스 등)만 base 후보로 삼는다
    tail = raw.rstrip()
    new_base = None
    if tail:
        last = tail[-1]
        if last.isalnum() or last in ('∑', ')', ']','}','₀','₁','₂','₃','₄','₅','₆','₇','₈','₉'):
            new_base = tail  # 단어 전체를 base 후보로 둔다 (A, B, n 등)
    return ''.join(out), new_base


def _paragraph_text(p: ET.Element) -> str:
    """
    문단 텍스트(OMML + 일반 첨자 처리 포함).
    """
    s = []
    base_hint: Optional[str] = None

    # 런 단위 순서 유지
    for r in p.findall('w:r', W_NS):
        piece, base_hint = _run_text_with_math(r, base_hint)
        if piece:
            s.append(piece)

    # 문단 직속 OMML도 합치기
    for m in p.findall('m:oMath', M_NS):
        s.append(_omml_text(m))
    for mp in p.findall('m:oMathPara', M_NS):
        s.append(_omml_text(mp))

    return ''.join(s).strip()

# =========================
# 표 파싱(병합 유지)
# =========================

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
    rowspans = defaultdict(int)
    active_v = {}  # col_idx -> start out_idx

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

# =========================
# DOCX → JSON
# =========================

def parse_docx_to_json(docx_file: io.BufferedIOBase | io.BytesIO | bytes | str,
                       with_paragraphs: bool = True) -> Dict[str, Any]:
    if isinstance(docx_file, str):
        with open(docx_file, 'rb') as f:
            data = f.read()
    elif isinstance(docx_file, (bytes, bytearray)):
        data = bytes(docx_file)
    elif hasattr(docx_file, 'read'):
        data = docx_file.read()
    else:
        raise TypeError("parse_docx_to_json: DOCX path/file/bytes only.")

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

# =========================
# CLI
# =========================

if __name__ == "__main__":
    import sys, json
    if not sys.argv[1:]:
        print("usage: python report_docx_parser.py <file.docx>")
        raise SystemExit(1)
    out = parse_docx_to_json(sys.argv[1], with_paragraphs=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
