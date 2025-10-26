# -*- coding: utf-8 -*-
import re
import zipfile
from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}

def norm_space(s: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", (s or "")).strip()

def get_text_runs(el) -> str:
    texts = []
    for t in el.xpath(".//w:t|.//m:t", namespaces=NS):
        if t.text:
            texts.append(t.text)
    return norm_space("".join(texts))

# ---------------- OMML → 선형 텍스트 (Σ 보완) ----------------
def omml_to_text(el) -> str:
    tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
    if tag in ("r", "t"):
        return norm_space(el.text or "")

    def J(e):
        return norm_space("".join(omml_to_text(c) for c in e)) if e is not None else ""

    if tag == "f":  # fraction
        num = J(el.find(".//m:num", NS))
        den = J(el.find(".//m:den", NS))
        if re.search(r"[+\-/* ]", num): num = f"({num})"
        if re.search(r"[+\-/* ]", den): den = f"({den})"
        return f"{num}/{den}"

    if tag in ("sSup", "sSub", "sSubSup"):
        base = J(el.find(".//m:e", NS))
        sup  = J(el.find(".//m:sup", NS))
        sub  = J(el.find(".//m:sub", NS))
        if tag == "sSup":   return f"{base}^{sup}"
        if tag == "sSub":   return f"{base}_{sub}"
        return f"{base}_{sub}^{sup}"

    if tag == "rad":
        deg = J(el.find(".//m:deg", NS))
        e   = J(el.find(".//m:e",   NS))
        return f"root({deg}, {e})" if deg else f"sqrt({e})"

    if tag == "d":
        beg = get_text_runs(el.find(".//m:begChr", NS)) or "("
        end = get_text_runs(el.find(".//m:endChr", NS)) or ")"
        e   = J(el.find(".//m:e", NS))
        return f"{beg}{e}{end}"

    if tag == "func":
        f_name = J(el.find(".//m:fName", NS) or el)
        arg    = J(el.find(".//m:e", NS) or el)
        return f"{f_name}({arg})"

    if tag == "nary":
        # Σ 기본값 + 하한/상한/표현 결합 (깨짐 방지)
        ch = el.find(".//m:chr", NS)
        sym = None
        if ch is not None and f"{{{NS['m']}}}val" in ch.attrib:
            sym = ch.attrib.get(f"{{{NS['m']}}}val")
        symbol = "∑"
        if sym and len(sym) == 1:
            symbol = sym  # 단일문자면 그대로 사용(∑, ∏ 등)
        sub  = J(el.find(".//m:sub", NS) or el)
        sup  = J(el.find(".//m:sup", NS) or el)
        expr = J(el.find(".//m:e",   NS) or el)
        left = symbol + (f"_{sub}" if sub else "") + (f"^{sup}" if sup else "")
        return f"{left}({expr})" if expr else left

    return J(el)

def paragraph_text_with_omml(p_el) -> str:
    parts = []
    for child in p_el.iter():
        qn = etree.QName(child.tag) if isinstance(child.tag, str) else None
        if not qn: 
            continue
        if qn.namespace == NS["m"]:
            if qn.localname in ("oMath","oMathPara","f","sSup","sSub","sSubSup","rad","d","func","nary"):
                parts.append(omml_to_text(child))
        elif qn.namespace == NS["w"] and qn.localname == "t":
            if child.text:
                parts.append(child.text)
    return norm_space(" ".join(parts)) or ""

# ---------------- 테이블 파서 (vMerge 정확화) ----------------
def parse_table(tbl_el):
    """
    Word 표(w:tbl) → [[row, col, rowspan, colspan, text], ...]
    - gridSpan → colspan
    - vMerge:
      * w:val="restart" → 앵커 생성, open_vmerge[col]=anchor_idx
      * w:val missing or "continue" → 위 앵커의 rowspan += 1, 현재 셀은 미출력
    """
    result = []
    occupied = set()         # (r,c) in current table
    open_vmerge = {}         # col -> index in result (ongoing vertical merge anchor)
    r_idx = 0

    rows = tbl_el.findall("./w:tr", NS)
    for tr in rows:
        r_idx += 1
        c_idx = 0

        # 한 행에서의 진행: 왼→오
        tcs = tr.findall("./w:tc", NS)
        for tc in tcs:
            # 다음 가용 col 찾기(이전 셀의 colspan으로 점유된 칸은 건너뜀)
            while (r_idx, c_idx + 1) in occupied:
                c_idx += 1
            c_idx += 1

            # colspan
            grid_span_el = tc.find(".//w:tcPr/w:gridSpan", NS)
            colspan = int(grid_span_el.attrib.get(f"{{{NS['w']}}}val")) if grid_span_el is not None else 1

            # vMerge 상태
            vmerge_el  = tc.find(".//w:tcPr/w:vMerge", NS)
            vmerge_val = (vmerge_el.attrib.get(f"{{{NS['w']}}}val") if vmerge_el is not None else None)
            v_state = "none"
            if vmerge_el is not None:
                v_state = "restart" if (vmerge_val == "restart") else "continue"

            # 셀 텍스트
            cell_text_parts = []
            for p in tc.findall(".//w:p", NS):
                t = paragraph_text_with_omml(p)
                if t:
                    cell_text_parts.append(t)
            text = norm_space("\n".join(cell_text_parts))

            # ---- 배치 로직 ----
            if v_state == "continue":
                # 진행 중인 vMerge 앵커를 찾아 rowspan 증가, 현재 셀은 미출력
                # (colspan>1이면 첫번째 유효 col의 앵커를 사용)
                anchor_idx = None
                for cc in range(c_idx, c_idx + colspan):
                    if cc in open_vmerge:
                        anchor_idx = open_vmerge[cc]
                        break
                if anchor_idx is None:
                    # 드물게 문서가 'continue'만 있고 상단 'restart'가 누락된 경우: 앵커 생성으로 보정
                    anchor_idx = len(result)
                    result.append([r_idx, c_idx, 1, colspan, text])
                    for cc in range(c_idx, c_idx + colspan):
                        open_vmerge[cc] = anchor_idx

                # 해당 앵커 rowspan +1
                result[anchor_idx][2] += 1

                # 현재 행의 점유만 마킹
                for cc in range(c_idx, c_idx + colspan):
                    occupied.add((r_idx, cc))
                continue  # 출력하지 않음

            # v_state == restart 또는 none: 새로운 셀 생성
            idx = len(result)
            result.append([r_idx, c_idx, 1, colspan, text])

            # 점유 마킹
            for cc in range(c_idx, c_idx + colspan):
                occupied.add((r_idx, cc))

            if v_state == "restart":
                # 새 앵커 시작
                for cc in range(c_idx, c_idx + colspan):
                    open_vmerge[cc] = idx
            else:
                # 세로 병합이 아닌 일반 셀: 이후 행부터는 해당 열의 병합이 아님
                for cc in range(c_idx, c_idx + colspan):
                    if cc in open_vmerge and open_vmerge[cc] == idx:
                        open_vmerge.pop(cc, None)

        # 행 종료 후: 아무 처리 필요 없음(다음 행에서 continue면 그대로 anchor 사용)

    return result

# ---------------- 라벨 탐지 ----------------
_re_numeric_label = re.compile(r"^\s*(\d+(?:\.\d+)*)([.)]?)\s+(.*)$")
_re_angle_label   = re.compile(r"^\s*<([^>]+)>\s*(.*)$")
_re_version_like  = re.compile(r"^\s*v\d+(?:\.\d+)+\s*$", re.IGNORECASE)

def detect_label(line: str):
    s = line.strip()
    m = _re_angle_label.match(s)
    if m:
        label = f"<{m.group(1)}>"
        rest  = m.group(2).strip()
        return True, 1, label, (rest if rest else None)

    m = _re_numeric_label.match(s)
    if m:
        head, _, rest = m.groups()
        if _re_version_like.match(head):
            return False, 0, "", None
        depth = head.count(".") + 1
        label = f"{head} {rest}".strip()
        return True, depth, label, None

    return False, 0, "", None

# ---------------- DOCX → flat ----------------
def extract_flat_from_docx(docx_path: str):
    with zipfile.ZipFile(docx_path) as zf:
        with zf.open("word/document.xml") as f:
            root = etree.fromstring(f.read())

    body = root.find(".//w:body", NS)
    if body is None:
        return []

    flat = []
    for el in body:
        tag = etree.QName(el).localname
        if tag == "p":
            text = paragraph_text_with_omml(el)
            if not text:
                continue
            is_label, depth, label, rest = detect_label(text)
            if is_label:
                flat.append({"_kind": "label", "depth": depth, "label": label})
                if rest:
                    flat.append({"_kind": "sen", "text": rest})
            else:
                flat.append({"_kind": "sen", "text": text})
        elif tag == "tbl":
            table = parse_table(el)
            flat.append({"_kind": "table", "table": table})
    return flat

# ---------------- flat → 트리 ----------------
def nest_blocks(flat):
    root = {"content": []}
    stack = [(0, root)]
    for b in flat:
        if b["_kind"] == "label":
            depth = b["depth"]
            node = {"label": b["label"], "content": []}
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack[-1][1]["content"].append(node)
            stack.append((depth, node))
        elif b["_kind"] == "sen":
            stack[-1][1]["content"].append({"sen": b["text"]})
        elif b["_kind"] == "table":
            stack[-1][1]["content"].append({"table": b["table"]})
    return root["content"]

# ---------------- 공개 API ----------------
def build_tree(docx_path: str):
    flat = extract_flat_from_docx(docx_path)
    content = nest_blocks(flat)
    return {"v": "1", "content": content}
