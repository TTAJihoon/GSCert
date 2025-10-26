# -*- coding: utf-8 -*-
"""
report_docx_parser.py

역할
- DOCX에서 표/문단/수식을 문서 흐름 순서대로 파싱하여 JSON으로 반환
- OMML(수식)은 선형 텍스트로 변환 (∑, 분수, 첨자, 괄호 등)
- 표 병합 정보(rowspan, colspan) 정확 반영
- meta 제거 (요구사항)
- 페이지 개념은 DOCX에 없으므로 다루지 않음 (목차 페이지 처리 등은 상위에서)

출력 예시
{
  "v": "1",
  "docx": {
    "v": "1",
    "content": [
      {"table": [[row, col, rowspan, colspan, "텍스트"], ...]},
      {"sen": "문단 텍스트"},
      ...
    ]
  }
}
"""
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

# ----------------------------
# OMML → 선형 텍스트 변환기
# ----------------------------

def _omml_text(el: ET.Element) -> str:
    """
    OMML 노드를 선형 텍스트로 변환.
    - 지원: nary(∑ 등), 분수(f), 첨자(sSup/sSub/sSubSup), 델리미터(d), 런(r), 수식문단(oMath/oMathPara)
    - 시그마 상/하한이 비어 있으면 생략(요구사항)
    """
    local = el.tag.split('}', 1)[-1]

    # 수식 문단 / 수식 컨테이너
    if local in ('oMathPara', 'oMath'):
        return ''.join(_omml_text(ch) for ch in list(el))

    # 수식 런: m:r 내부의 m:t 또는 w:t
    if local == 'r':
        out = []
        t = el.find('m:t', M_NS)
        if t is not None and t.text:
            out.append(t.text)
        # 런 안에 또 다른 수식/텍스트가 섞여 있을 수 있음
        for t2 in el.findall('w:t', W_NS):
            if t2.text:
                out.append(t2.text)
        for inner in el.findall('m:oMath', M_NS):
            out.append(_omml_text(inner))
        return ''.join(out)

    # 대형 연산자(∑ 등)
    if local == 'nary':
        # 연산자 문자
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

        # 상/하한 둘 다 비어 있으면 생략: ∑(body)
        # 하나라도 있으면만 _{sub}^{sup} 부착 (비어있는 쪽은 생략)
        limiter = ''
        if sub_txt and sup_txt:
            limiter = f"_{{{sub_txt}}}^{{{sup_txt}}}"
        elif sub_txt:
            limiter = f"_{{{sub_txt}}}"
        elif sup_txt:
            limiter = f"^{{{sup_txt}}}"

        return f"{op}{limiter}({body})"

    # 분수
    if local == 'f':
        num = _omml_text(el.find('m:num', M_NS)) or ''
        den = _omml_text(el.find('m:den', M_NS)) or ''
        return f"({num})/({den})"

    # 첨자/아래첨자/복합
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

    # 델리미터(괄호/절댓값 등)
    if local == 'd':
        beg = el.find('m:dPr/m:begChr', M_NS)
        end = el.find('m:dPr/m:endChr', M_NS)
        begc = beg.get(ET.QName(M_NS['m'], 'val')) if beg is not None else '('
        endc = end.get(ET.QName(M_NS['m'], 'val')) if end is not None else ')'
        inner = ''.join(_omml_text(c) for c in el.findall('m:e', M_NS))
        return f"{begc}{inner}{endc}"

    # 폴백: 내부 텍스트(w:t) 모으기
    return ''.join(t.text or '' for t in el.findall('.//w:t', W_NS))


def _run_text_with_math(r: ET.Element) -> str:
    """
    w:r 내부 텍스트/수식/심볼을 결합.
    """
    out = []

    # 심볼(w:sym): Cambria Math 등에서 사용
    sym = r.find('w:sym', W_NS)
    if sym is not None:
        ch = sym.get(WCHAR)
        if ch:
            try:
                out.append(chr(int(ch, 16)))
            except Exception:
                pass

    # 일반 텍스트
    for t in r.findall('w:t', W_NS):
        if t.text:
            out.append(t.text)

    # 런 내부 수식
    for m in r.findall('m:oMath', M_NS):
        out.append(_omml_text(m))

    return ''.join(out)


def _paragraph_text(p: ET.Element) -> str:
    """
    문단 텍스트(수식 포함)를 선형 문자열로.
    """
    s = []
    for r in p.findall('w:r', W_NS):
        s.append(_run_text_with_math(r))
    # 문단 직속 수식
    for m in p.findall('m:oMath', M_NS):
        s.append(_omml_text(m))
    for mp in p.findall('m:oMathPara', M_NS):
        s.append(_omml_text(mp))
    return ''.join(s).strip()

# ----------------------------
# 표 파싱 (병합 정확 반영)
# ----------------------------

def _cell_text(tc: ET.Element) -> str:
    # 셀 내부 문단 모으기 (수식 포함)
    lines = [_paragraph_text(p) for p in tc.findall('.//w:p', W_NS)]
    # 남은 수식 폴백
    for m in tc.findall('.//m:oMath', M_NS):
        txt = _omml_text(m)
        if txt:
            lines.append(txt)
    lines = [ln for ln in lines if ln]
    return '\n'.join(lines)


def _parse_table(tbl: ET.Element) -> Dict[str, Any]:
    """
    {"table": [[row, col, rowspan, colspan, text], ...]} 형태 반환
    - row/col 1-base
    - vMerge(세로) / gridSpan(가로) 반영
    """
    out: List[List[Any]] = []
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
                # 이어짐: 시작셀 rowspan만 +1
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

    # rowspan 반영
    for i, entry in enumerate(out):
        entry[2] = rowspans[i]

    return {"table": out}

# ----------------------------
# DOCX → JSON
# ----------------------------

def parse_docx_to_json(docx_file: io.BufferedIOBase | io.BytesIO | bytes | str,
                       with_paragraphs: bool = True) -> Dict[str, Any]:
    """
    DOCX만 입력으로 받는다.
    - 경로(str) or 파일객체 or 바이트
    """
    # DOCX 바이트 확보
    if isinstance(docx_file, str):
        with open(docx_file, 'rb') as f:
            data = f.read()
    elif isinstance(docx_file, (bytes, bytearray)):
        data = bytes(docx_file)
    elif hasattr(docx_file, 'read'):
        data = docx_file.read()
    else:
        raise TypeError("parse_docx_to_json: DOCX 파일 경로/파일객체/바이트만 지원합니다.")

    # document.xml 로드
    with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
        xml = zf.read('word/document.xml')

    root = ET.fromstring(xml)
    body = root.find('.//w:body', W_NS)

    content: List[Dict[str, Any]] = []
    if body is None:
        return {"v": "1", "docx": {"v": "1", "content": content}}

    # 문서 흐름 순서대로 p / tbl 순회 (상위 레벨)
    for child in list(body):
        tag = child.tag.split('}', 1)[-1]
        if tag == 'tbl':
            content.append(_parse_table(child))
        elif tag == 'p' and with_paragraphs:
            txt = _paragraph_text(child)
            if txt:
                content.append({"sen": txt})
        # 그 외 (섹션 구분 등)은 무시

    return {"v": "1", "docx": {"v": "1", "content": content}}


# CLI 테스트
if __name__ == "__main__":
    import sys, json
    if not sys.argv[1:]:
        print("usage: python report_docx_parser.py <file.docx>")
        raise SystemExit(1)
    out = parse_docx_to_json(sys.argv[1], with_paragraphs=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
