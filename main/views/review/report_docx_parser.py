# -*- coding: utf-8 -*-
"""
report_docx_parser.py
- DOCX를 DOM 순서대로 파싱해 문서 전체를 하나의 content로 반환
- (선택) PDF 각 페이지 상/하단 7%에서 텍스트 추출해 header/footer 배열로 제공
- 최종 스키마:
  {
    "v": "0.5",
    "content": [  # 문서 전체, 기존 규칙(label/sen/table) 유지
      {"label": "...", "content": [ {"sen":"..."}, {"table":[...]}, ... ]},
      {"sen": "..."},
      {"table": [[row,col,rowspan,colspan,"text"], ...]}
    ],
    "header": { "1": ["...","..."], "2": ["..."] },
    "footer": { "1": ["..."], "2": ["..."] }
  }

Windows Server 2022 / Django 환경에서 그대로 사용 가능.
"""

from __future__ import annotations
import io
import re
import zipfile
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

# ====== 외부 의존 (선택) ======
# PDF 텍스트 추출 (상/하단 7%): 필요 시 설치
#   pip install pdfplumber
try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover
    pdfplumber = None

# ====== 상수 ======
HEADER_BAND = 0.07  # 페이지 상단 7%
FOOTER_BAND = 0.07  # 페이지 하단 7%

# DOCX 네임스페이스
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


# ------------------------------------------------------------------------------
# Drop-in helpers: label 감지 / 앵커 / 표 앵커
# ------------------------------------------------------------------------------

_LABEL_PATTERNS = [
    # 1. / 1) / 1.1 / 1.1.1
    r"^\s*(\d+(?:\.\d+){0,3})[.)]\s+(.*)$",
    r"^\s*(\d+)\s+(.*)$",
    # A. / A) / a.
    r"^\s*([A-Za-z])[.)]\s+(.*)$",
    # Ⅰ. Ⅱ. Ⅲ.
    r"^\s*([Ⅰ-Ⅹ]+)[.)]\s+(.*)$",
    # 가. 나. 다. (한글 낱자)
    r"^\s*([가-힣])[.)]\s+(.*)$",
]
_LABEL_RE = [re.compile(p) for p in _LABEL_PATTERNS]


def _depth_from_label(label: str) -> int:
    # 1.1.1 → 3, Ⅰ → 1, A → 1, 가 → 1
    if re.match(r"^\d+(?:\.\d+)*$", label):
        return label.count(".") + 1
    return 1


def detect_label(text: str) -> Optional[Tuple[str, int, str]]:
    """
    텍스트가 '레이블 + 본문' 형태면 (label, depth, remainder) 반환, 아니면 None
    """
    s = (text or "").strip()
    if not s:
        return None
    for rx in _LABEL_RE:
        m = rx.match(s)
        if m:
            label = m.group(1).strip()
            remainder = (m.group(2) or "").strip()
            if not remainder:
                # "1."만 있고 본문이 없으면 라벨로 보지 않음
                return None
            depth = _depth_from_label(label)
            return (label, depth, remainder)
    return None


def make_para_anchor(text: str) -> str:
    """
    문단/문장 고유 Anchor(간단 해시). 프론트 링크 용도.
    """
    s = (text or "").strip()
    if not s:
        return ""
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
    head = re.sub(r"\s+", " ", s)[:20]
    return f"{head}-{h}"


def _table_anchors(cells: List[List[Any]]) -> Tuple[str, str]:
    """
    표의 첫 행에서 강한 앵커 후보를 간단 생성.
    반환: (strong_anchor, weak_anchor)
    """
    try:
        first_texts = []
        for r in cells:
            # r: [row, col, rowspan, colspan, text]
            if len(r) >= 5 and r[0] == 1:  # 첫 행
                first_texts.append(str(r[4] or "").strip())
        strong = make_para_anchor(" | ".join([t for t in first_texts if t][:3]) or "table")
        weak = make_para_anchor(f"table-size-{len(cells)}")
        return strong, weak
    except Exception:
        return make_para_anchor("table"), make_para_anchor("table-weak")


# ------------------------------------------------------------------------------
# OMML (수식) → 간단 텍스트화
# ------------------------------------------------------------------------------

def _concat_all_text(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.findall(".//w:t", NS)).strip()


def parse_omml_to_latex_like(omath: ET.Element) -> str:
    """
    OMML을 간단히 텍스트화/토큰치환 (정밀 LaTeX 변환 아님)
    """
    raw = ET.tostring(omath, encoding="unicode")
    txt = _concat_all_text(omath)
    # 흔한 토큰 대체(간단)
    txt = txt.replace("∑", r"\sum").replace("√", r"\sqrt").replace("±", r"\pm")
    txt = txt.replace("≤", r"\le").replace("≥", r"\ge").replace("≠", r"\ne")
    # 여백 정리
    return re.sub(r"\s+", " ", txt).strip() or raw[:60]


# ------------------------------------------------------------------------------
# 표 파서: gridSpan / vMerge 간단 지원
# ------------------------------------------------------------------------------
def parse_table_element(tbl: ET.Element) -> List[List[Any]]:
    """
    DOCX w:tbl → [[row, col, rowspan, colspan, text], ...]
    간단한 테이블 병합(gridSpan/vMerge) 처리.
    """
    rows = tbl.findall(".//w:tr", NS)
    # 스팬 추적용: (row,col) 자리 점유 여부
    grid: List[List[Optional[Dict[str, Any]]]] = []
    out: List[List[Any]] = []

    def next_free_col(row_slots: List[Optional[Dict[str, Any]]]) -> int:
        c = 1
        while c <= len(row_slots) and row_slots[c - 1] is not None:
            c += 1
        return c

    # 동적 최대 열 추적
    max_cols = 0

    # vMerge 추적: 세로 병합 중인 셀 관리 (열 인덱스 -> {start_row, text, colspan, rowspan})
    vmerge_track: Dict[int, Dict[str, Any]] = {}

    r_idx = 0
    for tr in rows:
        r_idx += 1
        row_slots: List[Optional[Dict[str, Any]]] = []

        # 기존 vMerge로 인해 이미 점유중인 슬롯 채우기
        max_cols = max(max_cols, len(vmerge_track))
        if len(row_slots) < max_cols:
            row_slots += [None] * (max_cols - len(row_slots))

        cells = tr.findall("./w:tc", NS)
        c_iter_idx = 0
        current_col = 1

        # vMerge로 내려와야 하는 열 슬롯 미리 반영
        if vmerge_track:
            # ensure row_slots size
            need_cols = max(vmerge_track.keys()) if vmerge_track else 0
            if len(row_slots) < need_cols:
                row_slots += [None] * (need_cols - len(row_slots))
            # mark occupied by vMerge continuations
            for col, info in list(vmerge_track.items()):
                # place a placeholder to mark occupied
                if len(row_slots) < col:
                    row_slots += [None] * (col - len(row_slots))
                row_slots[col - 1] = {"vmerge_cont": True}

        for tc in cells:
            c_iter_idx += 1
            # text
            txt = "".join(t.text or "" for t in tc.findall(".//w:t", NS)).strip()

            # spans
            gridSpan = 1
            gridSpanEl = tc.find(".//w:gridSpan", NS)
            if gridSpanEl is not None and gridSpanEl.get(f"{{{NS['w']}}}val"):
                try:
                    gridSpan = int(gridSpanEl.get(f"{{{NS['w']}}}val"))
                except Exception:
                    gridSpan = 1

            vMerge = tc.find(".//w:vMerge", NS)
            vMerge_val = vMerge.get(f"{{{NS['w']}}}val") if vMerge is not None else None

            # find next free col
            # expand row_slots as needed
            while True:
                # ensure row_slots big enough
                if len(row_slots) < current_col + gridSpan - 1:
                    row_slots += [None] * (current_col + gridSpan - 1 - len(row_slots))

                # check occupancy
                occupied = any(row_slots[current_col - 1 + k] is not None for k in range(gridSpan))
                if not occupied:
                    break
                current_col += 1

            col_start = current_col

            if vMerge is not None:
                if vMerge_val in (None, "continue"):
                    # 세로 병합 계속: 상단의 vmerge_track을 찾아 rowspan 증가
                    # 상단 셀의 col을 찾아야 한다. 가장 가까운 동일 col을 사용.
                    # 여기서는 col_start 열을 기준으로 이어붙임
                    info = vmerge_track.get(col_start)
                    if info:
                        info["rowspan"] += 1
                        # 본 행의 해당 슬롯들 점유 표시
                        for k in range(info["colspan"]):
                            if len(row_slots) < col_start + k:
                                row_slots += [None] * (col_start + k - len(row_slots))
                            row_slots[col_start - 1 + k] = {"vmerge_cont": True}
                    else:
                        # 상단 정보가 없는데 continue가 왔다면 신규 시작으로 처리
                        vmerge_track[col_start] = {"start_row": r_idx - 1, "text": "", "colspan": gridSpan, "rowspan": 2}
                        for k in range(gridSpan):
                            row_slots[col_start - 1 + k] = {"vmerge_cont": True}
                elif vMerge_val == "restart":
                    # 새로운 vMerge 시작
                    vmerge_track[col_start] = {"start_row": r_idx, "text": txt, "colspan": gridSpan, "rowspan": 1}
                    # 현재 행에 표시되지만 출력은 나중에
                    for k in range(gridSpan):
                        row_slots[col_start - 1 + k] = {"vmerge_head": True}
                else:
                    # 알 수 없는 값 -> 일반 셀로 처리
                    for k in range(gridSpan):
                        row_slots[col_start - 1 + k] = {"occupied": True}
                    out.append([r_idx, col_start, 1, gridSpan, txt])
                current_col = col_start + gridSpan
            else:
                # vMerge 아님: 일반 셀
                for k in range(gridSpan):
                    row_slots[col_start - 1 + k] = {"occupied": True}
                out.append([r_idx, col_start, 1, gridSpan, txt])
                current_col = col_start + gridSpan

        # 행 종료 시 max_cols 갱신
        max_cols = max(max_cols, len(row_slots))

        # vMerge head가 있고 본문 텍스트가 있었다면, 현재 행에도 head 실체를 기록
        for col, info in list(vmerge_track.items()):
            if info.get("start_row") == r_idx:
                # head row 출력
                out.append([r_idx, col, info["rowspan"], info["colspan"], info.get("text", "")])

    # vMerge가 아래 행까지 계속되었으면 head row에 충분한 rowspan이 들어가도록 이미 증가 처리됨.
    # 단, head row가 아닌 곳은 출력에 추가하지 않았음(표준적 표현)

    return out


# ------------------------------------------------------------------------------
# flat → nested (문서 전체 1회 중첩)
# ------------------------------------------------------------------------------
def nest_blocks(flat: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    label depth에 따라 중첩. label/sen/table 이외의 키는 제거.
    """
    root: List[Dict[str, Any]] = []
    stack: List[Tuple[int, Dict[str, Any]]] = []  # (depth, node)

    def append_to_current(node: Dict[str, Any]) -> None:
        if stack:
            stack[-1][1]["content"].append(node)
        else:
            root.append(node)

    for item in flat:
        kind = item.get("_kind")
        if kind == "label":
            depth = int(item.get("depth", 1))
            label = item.get("label", "").strip()
            new_node = {"label": label, "content": []}
            # 스택 정리
            while stack and stack[-1][0] >= depth:
                stack.pop()
            if stack:
                stack[-1][1]["content"].append(new_node)
            else:
                root.append(new_node)
            stack.append((depth, new_node))
        elif kind == "sen":
            append_to_current({"sen": item.get("sen", "")})
        elif kind == "table":
            cells = item.get("table", [])
            append_to_current({"table": cells})
        else:
            # 무시
            continue

    return root


# ------------------------------------------------------------------------------
# PDF: 각 페이지 상/하단 7%에서 텍스트 추출
# ------------------------------------------------------------------------------
def extract_pdf_pages(pdf_path: str) -> Tuple[List[Dict[str, Any]], int]:
    """
    상/하단 7%에서 텍스트 라인 배열을 추출.
    반환: ( [ { "page":1, "header":[...], "footer":[...] }, ... ], total_pages )
    """
    if not pdfplumber:
        return ([], 0)

    pages_out: List[Dict[str, Any]] = []
    total = 0

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            h = float(page.height)
            top_h = h * HEADER_BAND
            bot_h = h * FOOTER_BAND
            header_lines: List[str] = []
            footer_lines: List[str] = []

            # header
            try:
                with page.crop((0, h - top_h - (h - top_h), page.width, h)) as top:
                    # 위 영역은 y축 기준 확인이 헷갈릴 수 있어 간단히 lines로
                    txt = (top.extract_text() or "").strip()
                    if txt:
                        header_lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            except Exception:
                header_lines = []

            # footer
            try:
                with page.crop((0, 0, page.width, bot_h)) as bottom:
                    txt = (bottom.extract_text() or "").strip()
                    if txt:
                        footer_lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            except Exception:
                footer_lines = []

            pages_out.append({"page": i, "header": header_lines, "footer": footer_lines})

    return (pages_out, total)


# ------------------------------------------------------------------------------
# DOCX 본문 평탄화
# ------------------------------------------------------------------------------
def _iter_body_elements(body: ET.Element):
    for node in body:
        if not isinstance(node.tag, str):
            continue
        yield node


def build_pages(docx_path: str, pdf_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse DOCX to a single document-level content array (DOCX DOM order),
    and optionally extract per-page header/footer from PDF using top/bottom 7% bands.

    Returns schema:
    { "v":"0.5", "content":[...], "header": {"1":[...], ...}, "footer": {"1":[...], ...} }
    """
    # 1) DOCX XML 로드
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_xml = z.read("word/document.xml")
    tree = ET.parse(io.BytesIO(doc_xml))
    root = tree.getroot()
    body = root.find(".//w:body", NS)

    # 2) DOCX DOM 순서대로 평탄화
    flat: List[Dict[str, Any]] = []
    doc_hint = 0  # (섹션 힌트만 보존; 순서 결정엔 사용 안 함)

    def add_para_block(text: str, hint_page: int):
        det = detect_label(text)
        if det:
            label_str, depth, remainder = det
            flat.append({"_kind": "label", "label": label_str, "depth": depth, "_hint": hint_page})
            if remainder:
                flat.append({"_kind": "sen", "sen": remainder, "_hint": hint_page})
        else:
            flat.append({"_kind": "sen", "sen": text, "_hint": hint_page})

    if body is not None:
        for node in _iter_body_elements(body):
            tag = node.tag
            if tag.endswith("}p"):  # 문단
                text_runs = node.findall(".//w:t", NS)
                text = "".join([t.text or "" for t in text_runs]).strip()
                if text:
                    add_para_block(text, doc_hint)
                # 수식(OMML)을 라텍스 유사 문자열로 sen 처리
                for omath in node.findall(".//m:oMath", NS):
                    latex_like = parse_omml_to_latex_like(omath)
                    if latex_like:
                        flat.append({"_kind": "sen", "sen": latex_like, "_hint": doc_hint})
            elif tag.endswith("}tbl"):  # 표
                cells = parse_table_element(node)
                if cells:
                    strong, weak = _table_anchors(cells)
                    flat.append({"_kind": "table", "table": cells, "_anchor": strong, "_weak": weak, "_hint": doc_hint})
            # 섹션 분리 힌트 (순서에는 사용하지 않음)
            sect = node.find(".//w:sectPr/w:type", NS)
            if sect is not None and sect.get(f"{{{NS['w']}}}val") == "nextPage":
                doc_hint += 1

    # 3) 문서 전체를 한 번만 중첩
    content_all = nest_blocks(flat)

    # 4) PDF 상/하단 7% 영역에서 header/footer 추출 (선택)
    header_map: Dict[str, List[str]] = {}
    footer_map: Dict[str, List[str]] = {}
    if pdf_path:
        pages, _ = extract_pdf_pages(pdf_path)
        for p in pages:
            pn = str(p.get("page", ""))
            if not pn:
                continue
            header_map[pn] = p.get("header", []) or []
            footer_map[pn] = p.get("footer", []) or []

    # 5) 최종 스키마 반환
    return {"v": "0.5", "content": content_all, "header": header_map, "footer": footer_map}


# ------------------------------------------------------------------------------
# (선택) 단독 실행 테스트
# ------------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    import os

    if len(sys.argv) < 2:
        print("Usage: python report_docx_parser.py <docx_path> [pdf_path]")
        sys.exit(1)

    docx = sys.argv[1]
    pdf = sys.argv[2] if len(sys.argv) >= 3 else None
    if pdf and not os.path.exists(pdf):
        print(f"[warn] PDF not found: {pdf}, header/footer는 빈 맵으로 반환됩니다.")
        pdf = None

    result = build_pages(docx, pdf)
    print(json.dumps(result, ensure_ascii=False, indent=2))
