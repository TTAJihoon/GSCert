# -*- coding: utf-8 -*-
"""
extract_process2_docx_overview(byts, filename) :
- '시험성적서 및 시험결과서' 형식에서 아래 4가지를 추출
  1) 시험기간(상단~첫 '7. 시험방법' 전) 중 날짜 포함 라인
  2) 개요 및 특성(설명)
  3) 개요 및 특성(주요 기능) 목록
  4) 소요일수 합계(모든 표의 '소요일수/소요 일수' 열 숫자 합)
"""

from io import BytesIO
from zipfile import ZipFile
from lxml import etree
import re

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# ─────────────────────────────────────────────────────────────
# 결과 템플릿
# ─────────────────────────────────────────────────────────────
def _empty_process2():
    return {
        "시험기간": [],                 # list[str]
        "개요 및 특성(설명)": "",       # str
        "개요 및 특성(주요 기능)": [],  # list[str]
        "소요일수 합계": 0,            # int
    }

# ─────────────────────────────────────────────────────────────
# DOCX → word/document.xml 로드
# ─────────────────────────────────────────────────────────────
def _read_document_xml_from_docx_bytes(byts: bytes):
    with ZipFile(BytesIO(byts)) as zf:
        with zf.open("word/document.xml") as f:
            return etree.parse(f).getroot()

# ─────────────────────────────────────────────────────────────
# 텍스트 유틸
# ─────────────────────────────────────────────────────────────
def _tc_text(tc) -> str:
    """표 셀 텍스트: 줄바꿈/문단 유지"""
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
    # 공백 정리(줄바꿈은 유지)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def _paragraph_text(p):
    return "".join(t.text or "" for t in p.findall(".//w:t", namespaces=NS)).strip()

def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

# 문서 바디를 순서대로 직렬화: (kind, text) -> kind: 'p' | 'tbl_cell'
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

# ─────────────────────────────────────────────────────────────
# 1) 시험기간 : 날짜 포함 라인 수집 (상단~첫 '7. 시험방법' 전)
# ─────────────────────────────────────────────────────────────
# 날짜 탐지 패턴(여러 형식 지원)
_DATE_PATTERNS = [
    # 2025년 6월 23일 / 2025년 6월
    re.compile(r"\b(19|20)\d{2}\s*년\s*\d{1,2}\s*월(\s*\d{1,2}\s*일)?\b"),
    # 2024.12.24 / 2024-12-24 / 2024/12/24
    re.compile(r"\b(19|20)\d{2}\s*[./-]\s*(0?[1-9]|1[0-2])\s*[./-]\s*(0?[1-9]|[12]\d|3[01])\b"),
    # 01/15  (MM/DD)
    re.compile(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])\b"),
]
# 기간 예시 패턴(사용자 예시; 라인 내에 start~end가 연속 등장하는 경우)
_PERIOD_EXAMPLE = re.compile(
    r"(?:\((?P<label>[^)]+)\)\s*)?"
    r"(?P<start>\d{4}.*?(?:일|\\d))"
    r"\s*[~\-]?\s*[\r\n ]+"
    r"(?P<end>\d{4}.*?(?:일|\\d))"
)

def _contains_date_like(s: str) -> bool:
    if _PERIOD_EXAMPLE.search(s):
        return True
    for p in _DATE_PATTERNS:
        if p.search(s):
            return True
    return False

def _extract_period_lines(doc_root):
    lines = []
    for kind, text in _iterate_body_as_lines(doc_root):
        if "7. 시험방법" in text:
            break
        if _contains_date_like(text):
            lines.append(_normalize_ws(text))
    # 중복 제거(순서 보존)
    seen, out = set(), []
    for x in lines:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

# ─────────────────────────────────────────────────────────────
# 2) 개요 및 특성(설명) : "본 제품은" ~ "으로 주요 기능은 다음과 같다" 직전
# ─────────────────────────────────────────────────────────────
def _extract_description(doc_root):
    blob = "\n".join([text for _, text in _iterate_body_as_lines(doc_root)])
    # 엄격 → 완화 순으로 시도
    m = re.search(r"본\s*제품은\s*(?P<desc>.+?)\s*으로\s*주요\s*기능은\s*다음과\s*같다", blob, re.DOTALL)
    if not m:
        m = re.search(r"본\s*제품은\s*(?P<desc>.+?)\s*(?:으로|이며|로서)\s*주요\s*기능은\s*다음과\s*같", blob, re.DOTALL)
    return _normalize_ws(m.group("desc")) if m else ""

# ─────────────────────────────────────────────────────────────
# 3) 개요 및 특성(주요 기능) : "다음과 같다" 이후 ~ "※ 상세기능은" 직전
# ─────────────────────────────────────────────────────────────
def _extract_features(doc_root):
    blob = "\n".join([text for _, text in _iterate_body_as_lines(doc_root)])
    m = re.search(r"다음과\s*같다(?::|\.|\s)*\s*(?P<section>.*?)\s*(?:※\s*상세기능은|상세\s*기능은)", blob, re.DOTALL)
    if not m:
        return []
    section = m.group("section")

    # 불릿/숫자목록 우선
    items = re.findall(r"^\s*(?:[-–—•·○●▪◦\*]|\d+[.)])\s*(.+)$", section, flags=re.MULTILINE)
    if not items:
        # 불릿이 없으면 줄 단위
        items = [s.strip() for s in section.splitlines() if s.strip()]

    # 공백 정규화 + 중복 제거(순서 보존)
    seen, out = set(), []
    for it in items:
        itn = _normalize_ws(it)
        if itn and itn not in seen:
            seen.add(itn); out.append(itn)
    return out

# ─────────────────────────────────────────────────────────────
# 4) 소요일수 합계 : 모든 표에서 '소요일수' 헤더 열의 숫자 합계
# ─────────────────────────────────────────────────────────────
def _extract_tables(doc_root):
    return doc_root.findall(".//w:tbl", namespaces=NS)

def _table_to_rows(tbl):
    rows = []
    for tr in tbl.findall("./w:tr", namespaces=NS):
        cells = tr.findall("./w:tc", namespaces=NS)
        rows.append([_tc_text(tc) for tc in cells])
    return rows

def _parse_int_like(s: str):
    if s is None:
        return None
    s2 = re.sub(r"[,\s]", "", s)
    return int(s2) if re.fullmatch(r"\d+", s2) else None

def _sum_days(doc_root) -> int:
    total = 0
    for tbl in _extract_tables(doc_root):
        rows = _table_to_rows(tbl)
        if not rows:
            continue
        # 헤더에서 '소요일수/소요 일수' 위치 찾기
        header_idx = None
        col_idx = None
        for r_i, row in enumerate(rows):
            for c_i, cell in enumerate(row):
                if ("소요일수" in cell) or ("소요 일수" in cell):
                    header_idx = r_i
                    col_idx = c_i
                    break
            if header_idx is not None:
                break
        if header_idx is None or col_idx is None:
            continue
        # 숫자만 합산
        for r_i in range(header_idx + 1, len(rows)):
            row = rows[r_i]
            if col_idx >= len(row):
                continue
            n = _parse_int_like(row[col_idx])
            if n is not None:
                total += n
    return total

# ─────────────────────────────────────────────────────────────
# 메인: byts, filename → out
# ─────────────────────────────────────────────────────────────
def extract_process2_docx_overview(byts: bytes, filename: str):
    """
    Parameters
    ----------
    byts : bytes   # .docx 파일 바이트
    filename : str # 파일명(로그용; 파싱엔 미사용)

    Returns
    -------
    out : dict
      {
        "시험기간": [ ... ],
        "개요 및 특성(설명)": "...",
        "개요 및 특성(주요 기능)": [ ... ],
        "소요일수 합계": 0
      }
    """
    out = _empty_process2()

    # 문서 파싱
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception:
        return out

    # 1) 시험기간
    out["시험기간"] = _extract_period_lines(doc_root)

    # 2) 개요 및 특성(설명)
    out["개요 및 특성(설명)"] = _extract_description(doc_root)

    # 3) 개요 및 특성(주요 기능)
    out["개요 및 특성(주요 기능)"] = _extract_features(doc_root)

    # 4) 소요일수 합계
    out["소요일수 합계"] = _sum_days(doc_root)

    return out
