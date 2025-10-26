# -*- coding: utf-8 -*-
import re
import zipfile
from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}

# ---------- 유틸: 텍스트 정리 ----------
def norm_space(s: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", (s or "")).strip()

def get_text_runs(el) -> str:
    # w:t, m:t 모두 수집
    texts = []
    for t in el.xpath(".//w:t|.//m:t", namespaces=NS):
        if t.text:
            texts.append(t.text)
    return norm_space("".join(texts))

# ---------- OMML → 선형 텍스트 ----------
def omml_to_text(el) -> str:
    """
    OMML(수식)을 선형 텍스트로 변환.
    지원: 분수(m:f), 첨자(m:sSup/m:sSub/m:sSubSup), 근호(m:rad), 구분(m:d), 함수(m:func),
         N-ary(m:nary) - Σ를 포함하여 UTF-8 '∑'로 출력.
    기타 태그는 자식 재귀 결합으로 폴백.
    """
    tag = etree.QName(el).localname

    # 리프 텍스트
    if tag in ("r", "t"):
        return norm_space(el.text or "")

    # 공통 자식 텍스트 결합
    def join_children(e):
        return norm_space("".join(omml_to_text(c) for c in e))

    # ---- 구조별 처리 ----
    if tag == "f":  # fraction
        num = el.find(".//m:num", NS)
        den = el.find(".//m:den", NS)
        num_s = join_children(num) if num is not None else ""
        den_s = join_children(den) if den is not None else ""
        # 분자/분모에 공백·연산자 포함 시 괄호 보강
        if re.search(r"[+\-/* ]", num_s):
            num_s = f"({num_s})"
        if re.search(r"[+\-/* ]", den_s):
            den_s = f"({den_s})"
        return f"{num_s}/{den_s}"

    if tag in ("sSup", "sSub", "sSubSup"):
        base = el.find(".//m:e", NS)
        sup  = el.find(".//m:sup", NS)
        sub  = el.find(".//m:sub", NS)
        base_s = join_children(base) if base is not None else ""
        sup_s  = join_children(sup) if sup is not None else ""
        sub_s  = join_children(sub) if sub is not None else ""
        if tag == "sSup":
            return f"{base_s}^{sup_s}"
        if tag == "sSub":
            return f"{base_s}_{sub_s}"
        return f"{base_s}_{sub_s}^{sup_s}"

    if tag == "rad":  # radical
        deg = el.find(".//m:deg", NS)
        e   = el.find(".//m:e", NS)
        deg_s = join_children(deg) if deg is not None else ""
        e_s   = join_children(e) if e is not None else ""
        if deg is not None and deg_s:
            return f"root({deg_s}, {e_s})"
        return f"sqrt({e_s})"

    if tag == "d":  # delimiter (괄호류)
        beg = get_text_runs(el.find(".//m:begChr", NS)) or "("
        end = get_text_runs(el.find(".//m:endChr", NS)) or ")"
        e   = el.find(".//m:e", NS)
        e_s = join_children(e) if e is not None else ""
        return f"{beg}{e_s}{end}"

    if tag == "func":
        f_name = join_children(el.find(".//m:fName", NS) or el)
        arg    = join_children(el.find(".//m:e", NS) or el)
        return f"{f_name}({arg})"

    if tag == "nary":
        # ∑, ∏ 등 기호
        # 기본은 Σ(U+2211)로 출력하고, 하한/상한/피연산을 결합
        # 심볼은 m:chr@m:val 또는 m:naryPr/m:chr 에 들어올 수 있음
        ch = el.find(".//m:chr", NS)
        sym = None
        if ch is not None and "val" in ch.attrib:
            sym = ch.attrib.get(f"{{{NS['m']}}}val")
        # 기본값: Σ
        symbol = "∑"
        # 일부 값 매핑
        # U+2211 SUMMATION, U+220F N-ARY PRODUCT 등
        if sym:
            # sym이 '∑'처럼 직접 문자거나, '∑'에 해당하는 코드가 올 수 있음
            symbol = sym if len(sym) == 1 else symbol

        sub   = join_children(el.find(".//m:sub", NS) or el)
        sup   = join_children(el.find(".//m:sup", NS) or el)
        expr  = join_children(el.find(".//m:e",   NS) or el)

        left = symbol
        if sub:
            left += f"_{sub}"
        if sup:
            left += f"^{sup}"
        if expr:
            return f"{left}({expr})"
        return left

    # 기본 폴백: 자식 재귀 연결
    return join_children(el)


def paragraph_text_with_omml(p_el) -> str:
    """
    단락(w:p) 내부에서 일반 텍스트와 OMML 수식을 선형으로 합성
    """
    parts = []
    # OMML 혹은 텍스트 런 단위로 순회
    for child in p_el.iter():
        qn = etree.QName(child.tag) if isinstance(child.tag, str) else None
        if not qn:
            continue
        if qn.namespace == NS["m"]:
            # 최상위 m:oMath, m:oMathPara, 혹은 그 내부 구조
            # 수식 전체를 하나로 처리하기 위해 oMath/oMathPara 기준으로 끊어줌
            if qn.localname in ("oMath", "oMathPara", "f", "sSup", "sSub", "sSubSup", "rad", "d", "func", "nary"):
                parts.append(omml_to_text(child))
        elif qn.namespace == NS["w"] and qn.localname == "t":
            if child.text:
                parts.append(child.text)
    # 합치고 공백 정리
    return norm_space(" ".join(parts)) or ""


# ---------- 테이블 파서: 1-based 좌표, vMerge/gridSpan 처리 ----------
def parse_table(tbl_el):
    """
    Word 표(w:tbl) → 셀 배열 [[row, col, rowspan, colspan, text], ...]
    """
    rows = tbl_el.findall(".//w:tr", NS)
    # 열 수 추정: tblGrid 또는 첫 행의 gridSpan 합
    grid_cols = tbl_el.findall(".//w:tblGrid/w:gridCol", NS)
    ncols = len(grid_cols) if grid_cols else None

    # 점유표(occupied)로 rowspan/colspan 반영
    result = []
    occupied = {}  # (r,c) -> True
    r_idx = 0
    for tr in rows:
        r_idx += 1
        c_idx = 0

        tcs = tr.findall(".//w:tc", NS)
        for tc in tcs:
            # 다음 가용 col 찾기(점유 피하기)
            while (r_idx, c_idx + 1) in occupied:
                c_idx += 1
            c_idx += 1

            # colspan
            grid_span_el = tc.find(".//w:tcPr/w:gridSpan", NS)
            colspan = int(grid_span_el.attrib.get(f"{{{NS['w']}}}val")) if grid_span_el is not None else 1

            # rowspan (vMerge)
            vmerge_el = tc.find(".//w:tcPr/w:vMerge", NS)
            vmerge_val = (vmerge_el.attrib.get(f"{{{NS['w']}}}val") if vmerge_el is not None else None)
            # 텍스트 수집
            cell_text = []
            for p in tc.findall(".//w:p", NS):
                cell_text.append(paragraph_text_with_omml(p))
            text = norm_space("\n".join([t for t in cell_text if t]))

            if vmerge_el is not None and vmerge_val in (None, "continue"):
                # vMerge: continue 또는 val 미지정 → 상단 기원 셀에 rowspan 누적
                # 간단 구현: 현재 위치를 "점유"만 하고, 원 셀에 병합하도록 처리
                # 원 셀 탐색 (위에서부터 내려오며 같은 열)
                origin = None
                for rr in range(r_idx - 1, 0, -1):
                    if (rr, c_idx) in [(r, c) for r, c, *_ in result]:
                        # 이 간단 탐색은 정확치 않으므로 아래에서 보정
                        pass
                # 실제로는 별도 구조로 원 셀 추적이 깔끔하지만, 여기서는
                # "현재 셀은 표시하지 않고 점유만" 시킴
                # (rowspan은 아래 루프에서 재구성)
                origin = None

            # 셀 배치: 일단 현재 셀을 결과에 추가
            result.append([r_idx, c_idx, 1, colspan, text if text is not None else ""])

            # 점유 마크
            for cc in range(c_idx, c_idx + colspan):
                occupied[(r_idx, cc)] = True

            # vMerge 'continue'일 경우, 나중에 rowspan 계산을 위해 표시만
            if vmerge_el is not None and vmerge_val in (None, "continue"):
                # 위 셀을 찾아 rowspan 증가
                # 간단하면서 안전한 방법: 같은 col에서 위로 올라가며 최초 등장 셀을 origin으로
                for k in range(len(result) - 2, -1, -1):
                    r0, c0, rs0, cs0, _ = result[k]
                    if c0 <= c_idx <= (c0 + cs0 - 1):
                        if r0 < r_idx:
                            result[k][2] = rs0 + 1  # rowspan +1
                            break

    # ncols이 필요하면 후처리에서 검증 가능
    return result


# ---------- 라벨(헤딩) 탐지 ----------
_re_numeric_label = re.compile(r"^\s*(\d+(?:\.\d+)*)([.)]?)\s+(.*)$")
_re_angle_label   = re.compile(r"^\s*<([^>]+)>\s*(.*)$")
_re_version_like  = re.compile(r"^\s*v\d+(?:\.\d+)+\s*$", re.IGNORECASE)

def detect_label(line: str):
    """ 숫자형 '1.2. 제목' 또는 꺾쇠 '<요약> ...' 라벨 탐지.
        v1.2 같은 버전 문자열은 제외.
        return: (is_label: bool, depth: int, label_text: str, rest_text: str|None)
    """
    s = line.strip()
    # 꺾쇠 라벨
    m = _re_angle_label.match(s)
    if m:
        label = f"<{m.group(1)}>"
        rest  = m.group(2).strip()
        return True, 1, label, (rest if rest else None)

    # 숫자형
    m = _re_numeric_label.match(s)
    if m:
        head, _, rest = m.groups()
        # 버전 문자열 오인 방지
        if _re_version_like.match(head):
            return False, 0, "", None
        depth = head.count(".") + 1
        label = f"{head} {rest}".strip()
        return True, depth, label, None

    return False, 0, "", None


# ---------- DOCX 본문 순회 → flat ----------
def extract_flat_from_docx(docx_path: str):
    with zipfile.ZipFile(docx_path) as zf:
        with zf.open("word/document.xml") as f:
            root = etree.fromstring(f.read())

    body = root.find(".//w:body", NS)
    if body is None:
        return []

    flat = []  # [{"_kind":"label/sen/table", ...}, ...]
    for el in body:
        tag = etree.QName(el).localname
        if tag == "p":  # paragraph
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
        else:
            # 기타 요소(그림/섹션등)는 무시
            continue
    return flat


# ---------- flat → 중첩 트리 ----------
def nest_blocks(flat):
    """
    label이 섹션 노드가 되고, 그 아래에 sen/table이 들어가는 트리 생성
    입력 순서를 보존.
    """
    root = {"content": []}
    stack = [(0, root)]  # (depth, node)

    for b in flat:
        if b["_kind"] == "label":
            depth = b["depth"]
            node = {"label": b["label"], "content": []}
            # 적절한 부모 depth 찾기
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack[-1][1]["content"].append(node)
            stack.append((depth, node))
        elif b["_kind"] == "sen":
            stack[-1][1]["content"].append({"sen": b["text"]})
        elif b["_kind"] == "table":
            stack[-1][1]["content"].append({"table": b["table"]})
    return root["content"]


# ---------- 공개 API ----------
def build_tree(docx_path: str):
    """
    DOCX → 단일 트리 JSON 반환 (페이지 개념 없음, meta 없음)
    {
      "v": "1",
      "content": [ { "label": "...", "content": [ {"sen":...}, {"table":[...]}, ... ] }, {"sen":...}, ... ]
    }
    """
    flat = extract_flat_from_docx(docx_path)
    content = nest_blocks(flat)
    return {"v": "1", "content": content}
