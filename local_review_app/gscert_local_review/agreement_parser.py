"""'시험합의서'(.docx) 에서 회사명(국문)·제품명(국문)을 추출한다.

메인 서버의 검증된 파서(main/views/certy/prdinfo_parse_agreement.py) 로직을 로컬 앱으로
이식했다. 셀 텍스트는 줄바꿈을 보존해, 한 셀 안에 "국문명: ...\n영문명: ..." 처럼
여러 라벨이 있어도 정확히 분해한다.

- 회사명: 라벨 셀이 정확히 '국문명'(콜론 없음)이고, 바로 오른쪽 셀에 값이 있는 구조.
- 제품명: '제품명 및 버전' 값 셀 또는 임의 셀 안의 '국문명:' 뒤 인라인 값(콜론 있음).
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS = {"w": _W}
_T_TAG = f"{{{_W}}}t"
_BR_TAG = f"{{{_W}}}br"

_WS_RE = re.compile(r"[\s ]+")
_INLINE_WS_RE = re.compile(r"[ \t ]+")
_DASH_RE = re.compile("[-‐‑‒–—―]")
_PRODUCT_RE = re.compile(r"(?:^|\n)\s*국문명\s*:\s*([^\n]+)")


def _cell_text(tc) -> str:
    """셀 텍스트를 줄바꿈(<w:br>/문단)을 보존하며 추출한다."""
    parts: list[str] = []
    for p in tc.findall(".//w:p", _NS):
        buf: list[str] = []
        for node in p.iter():
            if node.tag == _T_TAG:
                buf.append(node.text or "")
            elif node.tag == _BR_TAG:
                buf.append("\n")
        parts.append("".join(buf))
    if not parts:
        parts = ["".join(t.text or "" for t in tc.findall(".//w:t", _NS))]
    text = "\n".join(parts)
    text = _INLINE_WS_RE.sub(" ", text)
    return text.strip()


def _all_table_rows(root) -> list[list[str]]:
    rows: list[list[str]] = []
    for tbl in root.findall(".//w:tbl", _NS):
        for tr in tbl.findall("w:tr", _NS):
            cells = tr.findall("w:tc", _NS)
            rows.append([_cell_text(tc) for tc in cells])
    return rows


def _norm(s: str) -> str:
    """라벨 비교용 정규화: 소문자 + 공백/개행/콜론/하이픈 제거."""
    if not s:
        return ""
    s2 = s.lower()
    s2 = _WS_RE.sub("", s2)
    s2 = s2.replace(":", "")
    s2 = _DASH_RE.sub("", s2)
    return s2


def _has_colon(s: str) -> bool:
    return ":" in (s or "")


def _next_cell(rows: list[list[str]], r_idx: int, c_idx: int) -> str:
    row = rows[r_idx]
    return row[c_idx + 1].strip() if (c_idx + 1 < len(row)) else ""


def _company_kr(rows: list[list[str]]) -> str:
    """회사명(국문): 셀이 정확히 '국문명'(콜론 없음) → 오른쪽 셀 값."""
    target = _norm("국문명")
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if _norm(cell) == target and not _has_colon(cell):
                value = _next_cell(rows, r_i, c_i)
                if value:
                    return value
    return ""


def _product_kr(rows: list[list[str]]) -> str:
    """제품명(국문): '국문명:' 뒤 인라인 값(콜론 있음)."""
    # (A) '제품명 및 버전' 라벨의 오른쪽 값 셀 안에서 '국문명:' 추출
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if "제품명 및 버전" in cell:
                match = _PRODUCT_RE.search(_next_cell(rows, r_i, c_i))
                if match:
                    return match.group(1).strip()

    # (B) 라벨 셀 자체가 '국문명:'(콜론 있음) → 오른쪽 셀
    target = _norm("국문명")
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if _has_colon(cell) and _norm(cell) == target:
                value = _next_cell(rows, r_i, c_i)
                if value:
                    return value

    # (C) 보강: 모든 셀에서 '국문명: 값' 인라인 패턴
    for row in rows:
        for cell in row:
            match = _PRODUCT_RE.search(cell)
            if match:
                return match.group(1).strip()
    return ""


def _parse_docx_bytes(data: bytes) -> tuple[str, str]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            document_xml = archive.read("word/document.xml")
    except (OSError, BadZipFile, KeyError):
        return "", ""
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError:
        return "", ""
    rows = _all_table_rows(root)
    return _company_kr(rows), _product_kr(rows)


def extract_agreement_names(path: Path) -> tuple[str, str]:
    """합의서에서 (회사명 국문, 제품명 국문) 을 반환한다. 실패 시 ("", "").

    - .docx/.docm: 그대로 파싱.
    - .doc(구형 바이너리): 공유 엔진의 변환(MS Word/LibreOffice)으로 .docx 로 바꿔 파싱.
      (변환 도구가 없으면 빈 값을 반환하고, 사용자는 수동 입력한다.)
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return "", ""
    if not data:
        return "", ""

    # PK(zip) 시그니처면 .docx 로 간주하고 바로 파싱.
    if data[:2] == b"PK":
        return _parse_docx_bytes(data)

    # 그 외(구형 .doc OLE)는 공유 엔진 변환을 재사용한다.
    try:
        from gscert_review_core import engine

        docx_bytes = engine._convert_doc_to_docx_bytes(data)
    except Exception:
        return "", ""
    return _parse_docx_bytes(docx_bytes)
