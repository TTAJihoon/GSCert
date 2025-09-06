# -*- coding: utf-8 -*-
"""
extract_process2_docx_overview(byts, filename):
- 기존 4개 항목(시험기간/개요 설명/주요 기능/소요일수 합계) 유지
- 추가:
  A) detect_security_omission_text(byts, filename): '보안성 시험을 생략함' 문장 탐지 및 지정 포맷 반환
  B) LLM 추천(classify SW & keywords): _extract_description + _extract_features 텍스트를 gpt-5-nano로 전송,
     {"SW": "...", "keyword1": "...", "keyword2": "..."} 파싱해 'AI추천' 키로 함께 리턴
"""

from io import BytesIO
from zipfile import ZipFile
from lxml import etree
import re
from typing import List, Tuple, Dict, Any

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

def _empty_process2():
    return {
        "시험기간": [],
        "개요 및 특성(설명)": "",
        "개요 및 특성(주요 기능)": [],
        "소요일수 합계": 0,
        # 추가
        "AI추천": {}  # {"SW": str, "keyword1": str, "keyword2": str}
    }

def _read_document_xml_from_docx_bytes(byts: bytes):
    with ZipFile(BytesIO(byts)) as zf:
        with zf.open("word/document.xml") as f:
            return etree.parse(f).getroot()

def _tc_text(tc) -> str:
    parts = []
    for p in tc.findall(".//w:p", namespaces=NS):
        buf = []
        for node in p.iter():
            if node.tag == "{%s}t" % NS["w"]:
                buf.append(node.text or "")
            elif node.tag == "{%s}br" % NS["w"]:
                buf.append("\n")
        parts.append("".join(buf))
    if not parts:
        parts = ["".join(t.text or "" for t in tc.findall(".//w:t", namespaces=NS))]
    text = "\n".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def _paragraph_text(p):
    return "".join(t.text or "" for t in p.findall(".//w:t", namespaces=NS)).strip()

def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _iterate_body_as_lines(doc_root):
    body = doc_root.find(".//w:body", namespaces=NS)
    for child in body:
        tag = etree.QName(child.tag).localname
        if tag == "p":
            txt = _paragraph_text(child)
            if txt:
                yield ("p", txt)
        elif tag == "tbl":
            for tr in child.findall("./w:tr", namespaces=NS):
                cells = tr.findall("./w:tc", namespaces=NS)
                for tc in cells:
                    t = _tc_text(tc)
                    if t:
                        for line in t.splitlines():
                            line = line.strip()
                            if line:
                                yield ("tbl_cell", line)

_DATE_PATTERNS = [
    re.compile(r"\b(19|20)\d{2}\s*년\s*\d{1,2}\s*월(\s*\d{1,2}\s*일)?\b"),
    re.compile(r"\b(19|20)\d{2}\s*[./-]\s*(0?[1-9]|1[0-2])\s*[./-]\s*(0?[1-9]|[12]\d|3[01])\b"),
    re.compile(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b"),
]
_PERIOD_EXAMPLE = re.compile(
    r"(?:\((?P<label>[^)]+)\)\s*)?"
    r"(?P<start>\d{4}.*?(?:일|\\d))"
    r"\s*[~\-]?\s*[\r\n ]+"
    r"(?P<end>\d{4}.*?(?:일|\\d))"
)

def _contains_date_like(s: str) -> bool:
    if _PERIOD_EXAMPLE.search(s): return True
    for p in _DATE_PATTERNS:
        if p.search(s): return True
    return False

def _extract_period_lines(doc_root):
    lines = []
    for kind, text in _iterate_body_as_lines(doc_root):
        if "7. 시험방법" in text:
            break
        if _contains_date_like(text):
            t = _normalize_ws(text)
            t = re.sub(r"^\s*(?:\d+\.\s*)?시험기간\s*[:：]\s*", "", t)
            lines.append(t)
    seen, out = set(), []
    for x in lines:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def _extract_description(doc_root):
    blob = "\n".join([text for _, text in _iterate_body_as_lines(doc_root)])
    m = re.search(r"본\s*제품은\s*(?P<desc>.+?)\s*으로\s*주요\s*기능은\s*다음과\s*같다", blob, re.DOTALL)
    if not m:
        m = re.search(r"본\s*제품은\s*(?P<desc>.+?)\s*(?:으로|이며|로서)\s*주요\s*기능은\s*다음과\s*같", blob, re.DOTALL)
    return _normalize_ws(m.group("desc")) if m else ""

def _extract_features(doc_root):
    blob = "\n".join([text for _, text in _iterate_body_as_lines(doc_root)])
    m = re.search(
        r"다음과\s*같다(?::|\.|\s)*\s*(?P<section>.*?)\s*(?:※\s*상세기능은|상세\s*기능은)",
        blob, re.DOTALL
    )
    if not m:
        return []
    section = m.group("section")
    items = re.findall(r"^\s*(?:[-–—•·○●▪◦\*]|\d+[.)])\s*(.+)$", section, flags=re.MULTILINE)
    if not items:
        items = [s.strip() for s in section.splitlines() if s.strip()]
    seen, out = set(), []
    for it in items:
        itn = _normalize_ws(it)
        if itn and itn not in seen:
            seen.add(itn)
            out.append(f"- {itn}")
    return out

def _extract_tables(doc_root):
    return doc_root.findall(".//w:tbl", namespaces=NS)

def _table_to_rows(tbl):
    rows = []
    for tr in tbl.findall("./w:tr", namespaces=NS):
        cells = tr.findall("./w:tc", namespaces=NS)
        rows.append([_tc_text(tc) for tc in cells])
    return rows

def _parse_int_like(s: str):
    if s is None: return None
    s2 = re.sub(r"[,\s]", "", s)
    return int(s2) if re.fullmatch(r"\d+", s2) else None

def _sum_days(doc_root) -> int:
    total = 0
    for tbl in _extract_tables(doc_root):
        rows = _table_to_rows(tbl)
        if not rows: continue
        header_idx = None; col_idx = None
        for r_i, row in enumerate(rows):
            for c_i, cell in enumerate(row):
                if ("소요일수" in cell) or ("소요 일수" in cell):
                    header_idx = r_i; col_idx = c_i; break
            if header_idx is not None: break
        if header_idx is None or col_idx is None: continue
        for r_i in range(header_idx + 1, len(rows)):
            row = rows[r_i]
            if col_idx >= len(row): continue
            n = _parse_int_like(row[col_idx])
            if n is not None: total += n
    return total

# ─────────────────────────────────────────────────────────────
# A) '보안성 시험을 생략함' → 지정 포맷 텍스트
# ─────────────────────────────────────────────────────────────
def detect_security_omission_text(byts: bytes, filename: str) -> str:
    """
    문서에 '보안성 시험을 생략함'을 포함한 '문장'이 있을 때:
      변수1 = 그 '문장'의 첫 글자부터 '을' or '를' 직전까지 (조사 제외)  → 예: '보안성 시험'
      변수2 = '바로 다음 문장'에서
              '인증번호: (****-****-**** ...)' + 줄바꿈 + '인증일: (yyyy-mm-dd)' 추출
      반환   = '{변수1}\n{변수2}'
    없으면 "-" 반환
    """
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception:
        return "-"

    lines = [text for _, text in _iterate_body_as_lines(doc_root)]
    # 문장 경계가 라인 단위로 들어온다고 가정(표/문단 혼재)
    idx = -1
    for i, ln in enumerate(lines):
        if "보안성 시험을 생략함" in ln:
            idx = i; break
    if idx < 0:
        return "-"

    sent = lines[idx]
    # '을/를' 앞 글자까지
    pos_eul = sent.find("을")
    pos_reul = sent.find("를")
    pos = None
    candidates = [p for p in [pos_eul, pos_reul] if p != -1]
    if candidates:
        pos = min(candidates)
    var1 = sent[:pos].strip() if pos is not None else sent.strip()

    # 바로 다음 문장에서 '인증번호'와 '인증일' 추출
    nxt = lines[idx + 1] if (idx + 1 < len(lines)) else ""
    # 다음 줄에 둘 다 한꺼번에 있을 수도, 줄바꿈 내장일 수도 있어 패턴을 여유있게
    m_num = re.search(r"인증번호\s*:\s*([0-9A-Za-z\-]+)", nxt)
    m_date = re.search(r"인증일\s*:\s*(\d{4}-\d{2}-\d{2})", nxt)
    var2 = ""
    if m_num and m_date:
        var2 = f"인증번호: {m_num.group(1)}\n인증일: {m_date.group(1)}"
    else:
        # 혹시 다음+다다음 줄로 분리된 경우 보정
        nxt2 = lines[idx + 2] if (idx + 2 < len(lines)) else ""
        num = m_num.group(1) if m_num else (re.search(r"인증번호\s*:\s*([0-9A-Za-z\-]+)", nxt2) or re.search(r"인증번호\s*:\s*([0-9A-Za-z\-]+)", nxt)).group(1) if (re.search(r"인증번호\s*:\s*([0-9A-Za-z\-]+)", nxt2) or re.search(r"인증번호\s*:\s*([0-9A-Za-z\-]+)", nxt)) else None
        date = m_date.group(1) if m_date else (re.search(r"인증일\s*:\s*(\d{4}-\d{2}-\d{2})", nxt2) or re.search(r"인증일\s*:\s*(\d{4}-\d{2}-\d{2})", nxt)).group(1) if (re.search(r"인증일\s*:\s*(\d{4}-\d{2}-\d{2})", nxt2) or re.search(r"인증일\s*:\s*(\d{4}-\d{2}-\d{2})", nxt)) else None
        if num and date:
            var2 = f"인증번호: {num}\n인증일: {date}"

    return f"{var1}\n{var2}" if (var1 and var2) else "-"

# ─────────────────────────────────────────────────────────────
# B) LLM 추천
# ─────────────────────────────────────────────────────────────
def _call_llm_for_sw(desc: str, features: List[str]) -> Dict[str, str]:
    """
    prdinfo_llm.classify_sw_and_keywords 사용.
    """
    try:
        from .prdinfo_llm import classify_sw_and_keywords
    except Exception:
        return {}
    text = (desc or "").strip()
    if features:
        text += "\n" + "\n".join(features)
    try:
        return classify_sw_and_keywords(text) or {}
    except Exception:
        return {}

# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def extract_process2_docx_overview(byts: bytes, filename: str):
    out = _empty_process2()
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception:
        return out

    out["시험기간"] = _extract_period_lines(doc_root)
    desc = _extract_description(doc_root)
    feats = _extract_features(doc_root)
    out["개요 및 특성(설명)"] = desc
    out["개요 및 특성(주요 기능)"] = feats
    out["소요일수 합계"] = _sum_days(doc_root)

    # LLM 추천 추가
    out["AI추천"] = _call_llm_for_sw(desc, feats)
    return out
