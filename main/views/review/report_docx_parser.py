# -*- coding: utf-8 -*-
"""
report_docx_parser.py
- DOCX(Word)에서 문단/표를 순서대로 파싱해 JSON으로 반환
- OMML(수식) → LaTeX 유사 선형 텍스트로 변환
- 표 병합(rowspan/colspan) 좌표 계산
- 라벨 탐지 규칙 유지
- 페이지 정보 미사용(선형 트리)

반환 예시:
{
  "v": "1",
  "content": [
    {"sen": "문장..."},
    {"label": "1 개요", "content": [...]},
    {"table": [[r,c,rowspan,colspan,text], ...]},
    ...
  ]
}
"""

from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile
from lxml import etree as ET
import re
from typing import List, Dict, Any, Optional, Tuple


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W_NS, "m": M_NS}

# -------------------------------
# OMML → 선형 텍스트 (핵심 개선)
# -------------------------------

def _cat(parts: List[str]) -> str:
    return "".join(parts)

def _text_all(node: ET._Element) -> str:
    parts = node.xpath(".//w:t | .//m:t", namespaces=NS)
    return "".join((p.text or "") for p in parts)

def omml_to_text(node: ET._Element) -> str:
    """
    OMML 수식 노드를 LaTeX 유사 선형 텍스트로 재귀 변환.
    - n-ary(시그마/파이): m:nary[m:sub/m:sup/m:e]
    - 분수: m:f[m:num, m:den]
    - 첨자: m:sSub/m:sSup/m:sSubSup
    - 괄호: m:d (m:dPr/m:begChr, m:endChr)
    - 루트, 오버바 등은 필요 최소만
    """
    tag = ET.QName(node).localname
    ns  = ET.QName(node).namespace

    # 기본 텍스트
    if tag == "t":
        return node.text or ""
    if tag == "r":
        tnodes = node.xpath(".//m:t | .//w:t", namespaces=NS)
        return tnodes[0].text if tnodes else ""

    # 수식 컨테이너
    if tag in ("oMathPara", "oMath"):
        return _cat([omml_to_text(ch) for ch in node])

    # n-ary (∑ 등)
    if tag == "nary":
        chr_node = node.find("./m:naryPr/m:chr", namespaces=NS)
        symbol = chr_node.get("{%s}val" % M_NS) if chr_node is not None else "∑"

        sub = node.find("./m:sub", namespaces=NS)
        sup = node.find("./m:sup", namespaces=NS)
        sub_txt = omml_to_text(sub) if sub is not None else ""
        sup_txt = omml_to_text(sup) if sup is not None else ""

        lims = ""
        if sub_txt:
            lims += f"_{{{sub_txt}}}"
        if sup_txt:
            lims += f"^{{{sup_txt}}}"

        base = node.find("./m:e", namespaces=NS)
        base_txt = omml_to_text(base) if base is not None else ""

        # 본문이 비면 ∑() 같은 빈 형태를 만들지 않도록 보호
        base_txt = base_txt.strip()
        if not base_txt:
            # 연산자만 출력하거나, 완전히 무시하는 선택지 중 택1
            return f"{symbol}{lims}"  # 여기선 연산자만 표시

        return f"{symbol}{lims} {base_txt}"

    # 분수
    if tag == "f":
        num = node.find("./m:num", namespaces=NS)
        den = node.find("./m:den", namespaces=NS)
        return f"({omml_to_text(num)})/({omml_to_text(den)})"

    # 첨자류
    if tag == "sSub":
        base = node.find("./m:e", namespaces=NS)
        sub  = node.find("./m:sub", namespaces=NS)
        return f"{omml_to_text(base)}_{{{omml_to_text(sub)}}}"
    if tag == "sSup":
        base = node.find("./m:e", namespaces=NS)
        sup  = node.find("./m:sup", namespaces=NS)
        return f"{omml_to_text(base)}^{{{omml_to_text(sup)}}}"
    if tag == "sSubSup":
        base = node.find("./m:e", namespaces=NS)
        sub  = node.find("./m:sub", namespaces=NS)
        sup  = node.find("./m:sup", namespaces=NS)
        return f"{omml_to_text(base)}_{{{omml_to_text(sub)}}}^{{{omml_to_text(sup)}}}"

    # 괄호 Delimiter
    if tag == "d":
        beg = node.find("./m:dPr/m:begChr", namespaces=NS)
        end = node.find("./m:dPr/m:endChr", namespaces=NS)
        begc = beg.get("{%s}val" % M_NS) if beg is not None else "("
        endc = end.get("{%s}val" % M_NS) if end is not None else ")"
        e = node.find("./m:e", namespaces=NS)
        return f"{begc}{omml_to_text(e)}{endc}"

    # 루트/오버바(필요 최소)
    if tag == "rad":  # sqrt / n-th root
        e = node.find("./m:e", namespaces=NS)
        deg = node.find("./m:deg", namespaces=NS)
        if deg is not None:
            return f"root[{omml_to_text(deg)}]({omml_to_text(e)})"
        return f"sqrt({omml_to_text(e)})"
    if tag == "bar":
        e = node.find("./m:e", namespaces=NS)
        return f"overline({omml_to_text(e)})"

    # 중간 컨테이너 통과
    if tag in ("e","num","den","sub","sup","box","groupChr","ctrlPr","rPr",
               "naryPr","dPr","deg","acc"):
        return _cat([omml_to_text(ch) for ch in node])

    # 그 외: 자식 재귀
    return _cat([omml_to_text(ch) for ch in node])


def para_text_with_math(w_p: ET._Element) -> str:
    """
    하나의 문단(w:p)을 순회하며 평문 + 수식을 순서 보존하여 선형 텍스트로 만든다.
    - 수식 블록(m:oMath, m:oMathPara)은 omml_to_text()로 치환
    - 나머지 w:t/m:t는 있는 그대로
    """
    out: List[str] = []
    # 문단 하위 노드를 **문서 순서대로** 훑는다
    for ch in w_p.iter():
        ns = ET.QName(ch).namespace
        tag = ET.QName(ch).localname

        # 수식 블록 발견 즉시 변환
        if ns == M_NS and tag in ("oMath", "oMathPara"):
            out.append(omml_to_text(ch))
            continue

        if (ns == W_NS and tag == "t") or (ns == M_NS and tag == "t"):
            if ch.text:
                out.append(ch.text)

    # 공백 정리 (여러 칸 → 한 칸)
    txt = " ".join("".join(out).split())
    return txt


# -------------------------------
# 테이블 파서 (병합 포함)
# -------------------------------

def _cell_text_with_math(tc: ET._Element) -> str:
    # 셀 안의 문단들을 합치되, 수식 변환 포함
    paras = tc.findall(".//w:p", namespaces=NS)
    parts = []
    for p in paras:
        parts.append(para_text_with_math(p))
    # 줄바꿈은 '\n'로 유지
    return "\n".join([s for s in parts if s])

def _table_grid(table: ET._Element) -> int:
    # w:tblGrid/w:gridCol로 열 수 추정 (없으면 행 내 최대 cell 개수로)
    grid_cols = table.findall(".//w:tblGrid/w:gridCol", namespaces=NS)
    if grid_cols:
        return len(grid_cols)
    # fallback: 첫 행의 셀 개수 기준 (gridSpan 반영 전)
    first_row = table.find(".//w:tr", namespaces=NS)
    if first_row is None:
        return 0
    cells = first_row.findall(".//w:tc", namespaces=NS)
    return max(1, len(cells))

def _parse_table(table: ET._Element) -> List[List[Any]]:
    """
    표를 (row, col, rowspan, colspan, text) 리스트로 반환.
    - 행/열 인덱스는 1-based
    - w:vMerge(세로 병합), w:gridSpan(가로 병합) 처리
    """
    rows = table.findall("./w:tr", namespaces=NS)
    if not rows:
        return []

    # 결과와 점유 상태 맵
    result: List[List[Any]] = []

    # 그리드 폭 추정(동적 확장 허용)
    max_cols_seen = 0

    # 세로병합 추적: (r,c) → anchor_row
    # 하지만 좌표는 우리가 직접 채울 것이므로, vMerge="continue"는 실제로 "위쪽 셀로 흡수"
    occupied: Dict[Tuple[int,int], bool] = {}

    # 각 행마다 실제 좌표 칸을 채우며 진행
    # cell place 헬퍼
    def next_free_col(r: int, start_c: int) -> int:
        c = start_c
        while occupied.get((r, c), False):
            c += 1
        return c

    cur_row_idx = 0
    # vMerge 그룹을 관리: (row, col) → (rowspan 증가)
    # 최종적으로는 anchor 셀(row,col)의 rowspan을 늘리고, continue 셀은 개별 레코드로 만들지 않음.
    anchors: Dict[Tuple[int,int], Dict[str,int]] = {}  # {(ar,ac): {"rowspan":N, "colspan":M}}

    for tr in rows:
        cur_row_idx += 1
        cur_col_idx = 1

        # 이번 행에서의 진행 열(occupied 피해서)
        cells = tr.findall("./w:tc", namespaces=NS)
        # 행 내 순회
        for tc in cells:
            cur_col_idx = next_free_col(cur_row_idx, cur_col_idx)

            # 병합 속성
            vmerge = tc.find(".//w:vMerge", namespaces=NS)
            gridspan = tc.find(".//w:gridSpan", namespaces=NS)
            colspan = int(gridspan.get("{%s}val" % W_NS)) if gridspan is not None else 1

            text = _cell_text_with_math(tc)

            if vmerge is not None:
                # 값이 없거나 "restart"면 앵커 시작
                vm_val = vmerge.get("{%s}val" % W_NS)
                if vm_val is None or vm_val == "restart":
                    # 일단 rowspan 1로 시작. 아래 행이 이어지는지 보면서 키움.
                    anchor_rc = (cur_row_idx, cur_col_idx)
                    anchors[anchor_rc] = {"rowspan": 1, "colspan": colspan}
                    # 가로 병합 영역 자리 점유
                    for dc in range(colspan):
                        occupied[(cur_row_idx, cur_col_idx + dc)] = True
                    # 결과에 우선 기록
                    result.append([cur_row_idx, cur_col_idx, 1, colspan, text])
                else:
                    # continue: 위쪽에서 시작된 anchor에 rowspan +1
                    # 현재 열 위치에 해당하는 anchor를 찾아야 함
                    # 같은 열 블록(가로 병합 포함) 내 앵커를 역추적
                    # 전략: 같은 컬럼 또는 동일 블록 시작열을 역으로 찾기
                    # 가장 가까운 위 행부터 내려오며 찾기
                    find_anchor = None
                    scan_row = cur_row_idx - 1
                    while scan_row >= 1 and find_anchor is None:
                        # 이 열부터 왼쪽으로 anchor가 있는지 체크 (colspan 고려)
                        for (ar, ac), meta in anchors.items():
                            if ar <= scan_row and (ac <= cur_col_idx < ac + meta["colspan"]):
                                # 이 블록 열 범위 안
                                # 그리고 anchor의 세로 범위가 scan_row~현재-1 포함해야 함
                                # 일단 anchor로 본다
                                find_anchor = (ar, ac)
                                break
                        scan_row -= 1
                    if find_anchor is not None:
                        anchors[find_anchor]["rowspan"] += 1
                        # 현재 자리 점유(가로 병합 폭만큼)
                        for dc in range(anchors[find_anchor]["colspan"]):
                            occupied[(cur_row_idx, (anchors[find_anchor]["colspan"] == 1 and cur_col_idx or find_anchor[1] + dc))] = True
                    # continue 셀은 개별 레코드 만들지 않음
            else:
                # 세로병합 없음: 일반 셀(가로 병합만 고려)
                # 자리 점유
                for dc in range(colspan):
                    occupied[(cur_row_idx, cur_col_idx + dc)] = True
                result.append([cur_row_idx, cur_col_idx, 1, colspan, text])

            max_cols_seen = max(max_cols_seen, cur_col_idx + colspan - 1)
            cur_col_idx += colspan

    # anchors 정보를 result에 반영(rowspan 업데이트)
    anchor_set = set(anchors.keys())
    for rec in result:
        r, c, rs, cs, t = rec
        if (r, c) in anchor_set:
            rec[2] = anchors[(r, c)]["rowspan"]  # rowspan 갱신

    return result


# -------------------------------
# 라벨 탐지(기존 규칙 유지)
# -------------------------------

LABEL_PATTERNS = [
    # "1 개요", "2.1 시험목적", "5.9 일반적 요구사항" 등
    re.compile(r"^\s*(\d+(\.\d+)*)\s+.+"),
    # "<첨부1>", "<첨부 2>" 등
    re.compile(r"^\s*<\s*첨부\s*\d+\s*>\s*$"),
    # "목 차" 단독
    re.compile(r"^\s*목\s*차\s*$"),
]

def is_label_line(text: str) -> bool:
    for pat in LABEL_PATTERNS:
        if pat.match(text):
            return True
    return False


# -------------------------------
# DOCX 문서 파싱
# -------------------------------

def parse_docx_bytes(docx_bytes: bytes) -> Dict[str, Any]:
    """
    DOCX 바이트를 받아 JSON 구조로 파싱.
    - 페이지 불문, 선형 순서 유지
    - 표와 문단을 문서 흐름대로
    """
    with ZipFile(BytesIO(docx_bytes)) as zf:
        with zf.open("word/document.xml") as f:
            xml = f.read()

    root = ET.fromstring(xml)

    body = root.find(".//w:body", namespaces=NS)
    if body is None:
        return {"v": "1", "content": []}

    content: List[Dict[str, Any]] = []

    # 문서 흐름: body.children = (p, tbl, p, tbl, ...)
    for child in body:
        tag = ET.QName(child).localname
        ns  = ET.QName(child).namespace

        if ns != W_NS:
            continue

        if tag == "p":  # 문단
            text = para_text_with_math(child).strip()
            if not text:
                continue

            if is_label_line(text):
                content.append({"label": text, "content": []})
            else:
                content.append({"sen": text})

        elif tag == "tbl":  # 표
            table_rows = _parse_table(child)
            if table_rows:
                content.append({"table": table_rows})

        elif tag == "sectPr":
            # 섹션 속성은 무시(페이지 처리 안함)
            continue

    return {"v": "1", "content": content}


# -------------------------------
# 외부에서 호출하는 진입점
# -------------------------------

def parse_docx(file_obj_or_bytes) -> Dict[str, Any]:
    """
    - Django/FileUpload 등 file-like 객체 또는 bytes 모두 지원
    """
    if isinstance(file_obj_or_bytes, (bytes, bytearray)):
        return {"v": "1", "content": parse_docx_bytes(file_obj_or_bytes)["content"]}
    # file-like
    data = file_obj_or_bytes.read()
    return {"v": "1", "content": parse_docx_bytes(data)["content"]}


# -------------------------------
# 로컬 테스트용 (선택)
# -------------------------------
if __name__ == "__main__":
    import sys, json
    with open(sys.argv[1], "rb") as f:
        out = parse_docx(f)
    print(json.dumps({"v": "1", "content": out["content"]}, ensure_ascii=False, indent=2))
