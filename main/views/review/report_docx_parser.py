# -*- coding: utf-8 -*-
"""
report_docx_parser.py
- DOCX -> JSON 파서 (페이지 무시, 단일 트리)
- 요구사항:
  * 표는 병합 좌표 (row, col, row_span, col_span, text)
  * 문단 수식: OMML -> 선형 텍스트 (∑ 하/상한, 분수, 첨자 등)
  * 수식이 들어간 child는 선형화된 수식만 반영하고, 평문 대체텍스트 꼬리는 버림
  * '목 차' 구간은 모두 sen으로만 수집
  * 라벨 탐지 규칙 유지 (숫자-목차/섹션, <첨부N> 등)
"""

import io
import re
import zipfile
from typing import List, Dict, Any, Optional, Tuple

from lxml import etree


# ------------- Namespaces -------------
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}


# ------------- Utilities -------------
def _norm_space(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u00A0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return s.strip()


def _join(parts: List[str]) -> str:
    out = "".join(parts)
    return (out
            .replace(" )", ")")
            .replace("( ", "(")
            .replace("_ {", "_{")
            .replace("^ {", "^{")
            )


# ------------- OMML (Math) linearization -------------
def _m_run_text(mr: etree._Element) -> str:
    # m:r 안의 m:t / w:t 둘 다 방어
    ts = mr.xpath(".//m:t/text()", namespaces=NS)
    if ts:
        return "".join(ts)
    ts = mr.xpath(".//w:t/text()", namespaces=NS)
    return "".join(ts)


def _m_sSub(node: etree._Element) -> str:
    base = parse_any(node.find("m:e", NS))
    sub  = parse_any(node.find("m:sub", NS))
    return f"{base}_{{{sub}}}" if sub else base


def _m_sSup(node: etree._Element) -> str:
    base = parse_any(node.find("m:e", NS))
    sup  = parse_any(node.find("m:sup", NS))
    return f"{base}^{{{sup}}}" if sup else base


def _m_sSubSup(node: etree._Element) -> str:
    base = parse_any(node.find("m:e", NS))
    sub  = parse_any(node.find("m:sub", NS))
    sup  = parse_any(node.find("m:sup", NS))
    if sub and sup:
        return f"{base}_{{{sub}}}^{{{sup}}}"
    if sub:
        return f"{base}_{{{sub}}}"
    if sup:
        return f"{base}^{{{sup}}}"
    return base


def _m_d(node: etree._Element) -> str:
    e = parse_any(node.find("m:e", NS))
    return f"({e})" if e else ""


def _m_frac(node: etree._Element) -> str:
    num = parse_any(node.find("m:num", NS))
    den = parse_any(node.find("m:den", NS))
    if not num and not den:
        return ""
    if num and den:
        return f"({num})/({den})"
    return num or den


def _m_nary(node: etree._Element) -> str:
    # ∑, ∏ 등
    chr_ = node.find("m:naryPr/m:chr", NS)
    op = chr_.get(f"{{{NS['m']}}}val") if chr_ is not None else "∑"

    # 하한/상한: sub/sup 또는 limLow/limUpp 모두 지원
    sub  = node.find("m:sub", NS)
    sup  = node.find("m:sup", NS)
    limL = node.find("m:limLow", NS)
    limU = node.find("m:limUpp", NS)

    body = parse_any(node.find("m:e", NS))

    lo = parse_any(sub) if sub is not None else (parse_any(limL) if limL is not None else "")
    up = parse_any(sup) if sup is not None else (parse_any(limU) if limU is not None else "")

    # 상/하한 공란이면 생략 (요구사항)
    if lo and up:
        return f"{op}_{{{lo}}}^{{{up}}} ({body})"
    if lo:
        return f"{op}_{{{lo}}} ({body})"
    if up:
        return f"{op}^{{{up}}} ({body})"
    return f"{op} ({body})"


def _m_oMath(node: etree._Element) -> str:
    parts: List[str] = []
    for ch in node:
        q = etree.QName(ch)
        if q.namespace != NS["m"]:
            continue
        name = q.localname
        if   name == "r":        parts.append(_m_run_text(ch))
        elif name == "f":        parts.append(_m_frac(ch))
        elif name == "nary":     parts.append(_m_nary(ch))
        elif name == "sSub":     parts.append(_m_sSub(ch))
        elif name == "sSup":     parts.append(_m_sSup(ch))
        elif name == "sSubSup":  parts.append(_m_sSubSup(ch))
        elif name == "d":        parts.append(_m_d(ch))
        elif name in ("oMath", "oMathPara"):
            parts.append(_m_oMath(ch))
        else:
            parts.append(parse_any(ch))
    return _join(parts)


def _m_oMathPara(node: etree._Element) -> str:
    inner = node.xpath("./m:oMath|./m:r|./m:f|./m:nary|./m:sSub|./m:sSup|./m:sSubSup|./m:d",
                       namespaces=NS)
    if not inner:
        return parse_any(node)
    parts = [parse_any(ch) for ch in inner]
    return _join(parts)


def parse_any(node: Optional[etree._Element]) -> str:
    if node is None:
        return ""
    q = etree.QName(node)
    if q.namespace != NS["m"]:
        ts = node.xpath(".//m:t/text()|.//w:t/text()", namespaces=NS)
        return "".join(ts)

    name = q.localname
    if   name == "oMathPara": return _m_oMathPara(node)
    if   name == "oMath":     return _m_oMath(node)
    if   name == "r":         return _m_run_text(node)
    if   name == "f":         return _m_frac(node)
    if   name == "nary":      return _m_nary(node)
    if   name == "sSub":      return _m_sSub(node)
    if   name == "sSup":      return _m_sSup(node)
    if   name == "sSubSup":   return _m_sSubSup(node)
    if   name == "d":         return _m_d(node)

    parts = [parse_any(ch) for ch in node]
    if parts:
        return _join(parts)
    ts = node.xpath(".//m:t/text()|.//w:t/text()", namespaces=NS)
    return "".join(ts)


def _paragraph_text_without_math(w_p: etree._Element) -> str:
    out: List[str] = []
    for child in w_p:
        q = etree.QName(child)

        # 1) 수식 컨테이너는 선형화 결과만
        if q.namespace == NS["m"] and q.localname in ("oMath", "oMathPara"):
            out.append(parse_any(child))
            continue

        # 2) 자손 어딘가에 수식 있으면 → 수식만 모으고 평문 꼬리(대체 텍스트)는 버림
        math_nodes = child.xpath(".//m:oMath|.//m:oMathPara", namespaces=NS)
        if math_nodes:
            for mn in math_nodes:
                out.append(parse_any(mn))
            continue

        # 3) 평문만 있으면 텍스트만 (AlternateContent는 통째 제거)
        child_copy = etree.fromstring(etree.tostring(child))
        for ac in child_copy.xpath(".//mc:AlternateContent", namespaces=NS):
            ac.getparent().remove(ac)
        wts = child_copy.xpath(".//w:t/text()", namespaces=NS)
        if wts:
            out.append("".join(wts))

    return _norm_space(_join([s for s in out if s]))


# ------------- Table extraction (with merges) -------------
def _cell_text(w_tc: etree._Element) -> str:
    # 모든 문단을 수집 + 수식 선형화 적용
    ps = w_tc.xpath(".//w:p", namespaces=NS)
    parts = [_paragraph_text_without_math(p) for p in ps]
    # 빈 줄 정리
    parts = [p for p in parts if p]
    return "\n".join(parts)


def _build_table_matrix(w_tbl: etree._Element) -> List[List[Optional[Dict[str, Any]]]]:
    """
    표의 병합을 풀어 실좌표 행렬을 구성한다.
    각 실좌표에 {'rspan':1.., 'cspan':1.., 'text':...,'root':(r,c)} 저장.
    """
    rows = w_tbl.xpath("./w:tr", namespaces=NS)
    matrix: List[List[Optional[Dict[str, Any]]]] = []
    # 각 행에서 column 포인터 이동하며 gridSpan, vMerge 처리
    # vMerge: 'restart' 시작점에서 아래로 같은 셀 확장
    # gridSpan: 가로 확장
    # Word는 명시적으로 컬럼수 정의가 어려워, 행마다 채우며 확장
    merge_down: Dict[Tuple[int, int], int] = {}  # (r,c) -> 남은 rspan

    for r_idx, tr in enumerate(rows, start=1):
        # ensure row exists
        if len(matrix) < r_idx:
            matrix.append([])

        c_ptr = 1
        tcs = tr.xpath("./w:tc", namespaces=NS)

        # carry-over (위에서 내려온 vMerge 채움)
        # 먼저 이 행의 시작 단계에서 matrix[r_idx-1]를 필요한 만큼 확장
        while len(matrix[r_idx - 1]) < max([c for (_, c) in merge_down.keys()] + [0]):
            matrix[r_idx - 1].append(None)

        # 이전 행에서 이어지는 vMerge들을 이 행에 심어둔다
        new_merge_down: Dict[Tuple[int, int], int] = {}
        for (root_r, root_c), rem in merge_down.items():
            if rem > 1:
                # 이 행의 해당 컬럼까지 빈 자리 채우기
                while len(matrix[r_idx - 1]) < root_c:
                    matrix[r_idx - 1].append(None)
                # 자리 빈칸 채움
                while len(matrix[r_idx - 1]) < root_c:
                    matrix[r_idx - 1].append(None)
                # 이 위치가 이미 채워졌으면 다음 빈칸 찾기
                # (일반적으로는 정확히 root_c에 들어가야 함)
                while len(matrix[r_idx - 1]) < root_c:
                    matrix[r_idx - 1].append(None)
                # 아래 행(r_idx)에 root_c까지 확보
                # (아래에서 채울 때 실제 값은 root 셀 참조로만 남김)
                new_merge_down[(root_r, root_c)] = rem - 1

        # 이 행을 채울 임시 리스트
        current_row: List[Optional[Dict[str, Any]]] = []
        # vMerge로 내려온 셀을 미리 채우자
        for (root_r, root_c), rem in merge_down.items():
            if rem > 0:
                # 해당 root_c 인덱스까지 빈칸 채움
                while len(current_row) < root_c - 1:
                    current_row.append(None)
                # 채운 위치에 placeholder
                current_row.append({"root": (root_r, root_c)})

        # 이제 실제 tc들을 순서대로 배치
        for tc in tcs:
            # gridSpan
            grid_span = 1
            gs = tc.xpath(".//w:gridSpan/@w:val", namespaces=NS)
            if gs:
                try:
                    grid_span = int(gs[0])
                except Exception:
                    grid_span = 1

            # vMerge
            vmerge_val = tc.xpath(".//w:vMerge/@w:val", namespaces=NS)
            vmerge_val = vmerge_val[0] if vmerge_val else None  # 'restart' | None(continue)

            # text
            text = _cell_text(tc)

            # current_row에서 첫 빈칸 위치 찾기
            col = 1
            while True:
                if col > len(current_row):
                    # append 영역
                    break
                if current_row[col - 1] is None:
                    break
                col += 1
            while len(current_row) < col - 1:
                current_row.append(None)

            # 셀 배치
            entry = {
                "rspan": 1,
                "cspan": grid_span,
                "text": text,
                "root": None,  # root 셀 자체
            }

            # vMerge 시작이면 아래로 확장 추후 적용
            if vmerge_val == "restart":
                # rspan은 아래 행에서 같은 root를 카운트하며 늘려준다.
                # 일단 여기선 1로 두고, carry-down dict에 추가
                pass
            elif vmerge_val is None:
                # vMerge 계속 (위에서 내려온 셀의 일부) → 이 tc는 보통 오지 않음
                # 혹 오더라도 텍스트는 무시하고 root 참조만 두는 것이 자연스럽다.
                pass

            # col~col+grid_span-1 까지 채움
            while len(current_row) < col - 1:
                current_row.append(None)
            for _ in range(grid_span):
                current_row.append({"root": (r_idx, col)})

            # 루트 위치에 실제 entry 저장
            current_row[col - 1] = entry

            # vMerge 'restart'인 경우, merge_down에 등록 (아래 행 rspan 증가)
            if vmerge_val == "restart":
                # 일단 1로 두고, 아래 행에서 동일 root를 만나면 rem을 누적 증가시킬 수 있게
                new_merge_down[(r_idx, col)] = new_merge_down.get((r_idx, col), 1) + 1
                # 실제 rspan 계산은 사후 한 번에 하자

        # 행 완성
        matrix[r_idx - 1] = current_row
        merge_down = {
            k: v for k, v in new_merge_down.items()
        }

    # rspan 재계산: root 기준으로 아래 행에서 같은 root 참조 몇 줄인지 센다
    R = len(matrix)
    for r in range(R):
        row = matrix[r]
        if row is None:
            continue
        C = len(row)
        for c in range(C):
            cell = row[c]
            if cell and cell.get("root") is None:
                # root 셀
                root_r, root_c = (r + 1, c + 1)
                rspan = 1
                rr = r + 1
                while rr < R:
                    crow = matrix[rr]
                    if root_c - 1 < len(crow) and crow[root_c - 1] and crow[root_c - 1].get("root") == (root_r, root_c):
                        rspan += 1
                        rr += 1
                    else:
                        break
                cell["rspan"] = rspan

    return matrix


def _emit_table(matrix: List[List[Optional[Dict[str, Any]]]]) -> Dict[str, Any]:
    items: List[List[Any]] = []
    R = len(matrix)
    for r in range(R):
        row = matrix[r]
        C = len(row)
        for c in range(C):
            cell = row[c]
            if not cell:
                continue
            if cell.get("root") is None:
                # root 셀
                text = cell.get("text", "")
                rspan = int(cell.get("rspan", 1))
                cspan = int(cell.get("cspan", 1))
                items.append([r + 1, c + 1, rspan, cspan, text])
    return {"table": items}


# ------------- Label detection / TOC handling -------------
_re_label = re.compile(r"^(?:\d+(?:\.\d+)*)\s+")
_re_attach = re.compile(r"^<\s*첨부\s*\d+\s*>")
_re_pure_toc_line = re.compile(r".+\s+\d+$")  # "제목 ... 7" 형태

def _is_label_line(text: str) -> bool:
    return bool(_re_label.match(text)) or bool(_re_attach.match(text))


def _is_toc_trigger(text: str) -> bool:
    return "목 차" in text.replace(" ", "")


def _is_toc_item(text: str) -> bool:
    # "제목 ... pageNum" 패턴이거나 점선 포함 등
    t = text.strip()
    if _re_pure_toc_line.search(t):
        return True
    # '..... 12' 같이 점선도 허용
    if re.search(r"\.{3,}\s*\d+$", t):
        return True
    # 라벨처럼 보이지만 끝에 페이지 숫자가 붙는 경우
    if _re_label.match(t) and re.search(r"\s\d+$", t):
        return True
    return False


# ------------- Document walk (w:tbl/w:p in order) -------------
def _walk_blocks(w_body: etree._Element):
    for child in w_body:
        q = etree.QName(child)
        if q.namespace != NS["w"]:
            continue
        name = q.localname
        if name == "tbl":
            yield ("tbl", child)
        elif name == "p":
            yield ("p", child)
        # 그림 등 다른 블록은 스킵


def _parse_blocks_to_content(w_body: etree._Element) -> List[Dict[str, Any]]:
    """
    문서의 블록(w:tbl/w:p)을 순회하여 content 리스트 생성.
    - TOC 모드: '목 차' 발견 ~ 비유사 항목까지 sen만 배출
    - 표: table 구조로 배출
    - 라벨: label/content 트리 단일 깊이(부제목은 content 안에 중첩) — 규칙 유지하되 과도한 추론은 지양
    """
    out: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []  # label 트리용

    toc_mode = False
    toc_cooldown = 0  # 목차 종료 판단용(연속해서 TOC 아닌 줄 만나면 종료)

    for kind, node in _walk_blocks(w_body):
        if kind == "tbl":
            matrix = _build_table_matrix(node)
            tbl_obj = _emit_table(matrix)

            # TOC 중에도 표는 그냥 테이블로 배출
            _append_node(out, stack, tbl_obj)
            continue

        # paragraph
        text = _paragraph_text_without_math(node)
        if not text:
            continue

        # TOC 모드 진입/유지/탈출
        if _is_toc_trigger(text):
            toc_mode = True
            toc_cooldown = 0
            _append_node(out, stack, {"sen": text})
            continue

        if toc_mode:
            if _is_toc_item(text):
                _append_node(out, stack, {"sen": text})
                toc_cooldown = 0
                continue
            else:
                # TOC가 아닌 줄이 일정 횟수 나오면 종료
                toc_cooldown += 1
                if toc_cooldown >= 2:  # 2줄 연속 비-TOC면 종료
                    toc_mode = False
                    toc_cooldown = 0
                # 현재 줄은 일반 규칙으로 처리 (fall-through)

        # 일반 라벨/문장 처리
        if _is_label_line(text):
            # 상위/하위 레벨 추정 (1, 1.1, 1.2, 2, ...)
            level = text.split()[0]
            depth = level.count(".") + 1  # "1"→1, "1.2"→2, ...
            # 새 label 노드
            node_obj = {"label": text, "content": []}
            _push_label(out, stack, node_obj, depth)
        else:
            _append_node(out, stack, {"sen": text})

    return out


def _push_label(out: List[Dict[str, Any]],
                stack: List[Dict[str, Any]],
                node_obj: Dict[str, Any],
                depth: int) -> None:
    # depth에 맞춰 stack 조정 후 append
    if depth <= 0:
        out.append(node_obj)
        return
    # stack 길이를 depth-1로 자르고, 거기에 붙임
    while len(stack) >= depth:
        stack.pop()
    if not stack:
        out.append(node_obj)
        stack.append(node_obj)
        return
    # 부모는 stack[-1]
    parent = stack[-1]
    parent["content"].append(node_obj)
    stack.append(node_obj)


def _append_node(out: List[Dict[str, Any]],
                 stack: List[Dict[str, Any]],
                 node_obj: Dict[str, Any]) -> None:
    if stack:
        stack[-1]["content"].append(node_obj)
    else:
        out.append(node_obj)


# ------------- DOCX loader -------------
def _load_document_xml(docx_bytes: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        with zf.open("word/document.xml") as f:
            xml = f.read()
    return etree.fromstring(xml)


# ------------- Public API (keep function name) -------------
def parse_docx(file_obj) -> Dict[str, Any]:
    """
    Entry point (함수명 유지):
      - Django InMemoryUploadedFile, TemporaryUploadedFile, file path, bytes 모두 가능
    Return:
      { "v":"1", "content":[ ... ] }
    """
    # read bytes
    if hasattr(file_obj, "read"):
        # UploadedFile 계열
        data = file_obj.read()
        # 재사용을 위해 포인터 되돌림(호출부가 다시 쓸 수도 있으므로)
        try:
            file_obj.seek(0)
        except Exception:
            pass
    elif isinstance(file_obj, (bytes, bytearray)):
        data = bytes(file_obj)
    elif isinstance(file_obj, str):
        # path
        with open(file_obj, "rb") as fp:
            data = fp.read()
    else:
        raise TypeError(f"Unsupported docx input type: {type(file_obj)}")

    # parse document.xml
    root = _load_document_xml(data)
    body = root.find(".//w:body", NS)
    if body is None:
        return {"v": "1", "content": []}

    content = _parse_blocks_to_content(body)

    return {
        "v": "1",
        "content": content,
    }
