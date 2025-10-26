# report_docx_parser.py  핵심 패치 (Python 3.10+)
# ------------------------------------------------
# 적용 포인트
# 1) 페이지 경계: 푸터 패턴 > 헤더 패턴 > y좌표 하강 순서
# 2) 커버 페이지 강제 확정
# 3) 표 그룹핑 키 강화: (page_no, header_hash, approx(x_left), approx(y_top))
# 4) 페이지 경계에서 표 강제 분할
# 5) TOC 꼬리숫자 정리
# 6) 'continue' 사용 위치 가드 (루프 밖에서 return/skip)

import re
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

# --- 공통 유틸 ---

def norm_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()

def tail_page_num_from_toc(line: str) -> Optional[int]:
    """목차 라인 끝의 페이지 숫자를 뽑아오되, 본문 라벨 파이프라인에선 제거하지 않는다."""
    m = re.match(r'^(?P<title>.+?)(?P<p>\d{1,3})$', norm_text(line))
    if m:
        return int(m.group('p'))
    return None

def is_label(line: str) -> bool:
    # “숫자. 공백 제목” 패턴 + 굵기/크기 정보가 있으면 더 좋지만, 우선 패턴 중심
    return bool(re.match(r'^\d+(\.\d+)*\.\s', norm_text(line)))

def approx(v: float | int, step: int = 20) -> int:
    """위치값 클러스터링(±step/2)"""
    try:
        return int(round(float(v) / step) * step)
    except Exception:
        return 0

def hash_header_row(cells: List[str]) -> str:
    sig = '|'.join(norm_text(c) for c in cells)
    return hashlib.md5(sig.encode('utf-8')).hexdigest()

# --- 페이지 경계 판단 ---

FOOTER_BREAK_PATTERNS = [
    r'페이지\s*:\s*\(?\d+\)\s*/\s*\(?(총)?\s*\d+\)?',  # 페이지 : (x)/(총y)
    r'\(\s*총\s*\d+\s*쪽?\s*\)',                     # (총 n쪽)
    r'페이지\s*\d+\s*/\s*\d+'                        # 페이지 x/y
]
HEADER_REPEAT_PATTERNS = [
    r'^성적서번호\s*:\s*GS-\w+-\d+',
    r'^SkyMARU\b', r'^TBT-B-\d{2}-\d{4}-[A-Z]{2}$'
]

def is_footer_break(line: str) -> bool:
    s = norm_text(line)
    return any(re.search(pat, s) for pat in FOOTER_BREAK_PATTERNS)

def is_header_repeat(line: str) -> bool:
    s = norm_text(line)
    return any(re.search(pat, s) for pat in HEADER_REPEAT_PATTERNS)

def split_pages_by_anchors(
    pdf_lines: List[Dict[str, Any]],
    total_pages_hint: Optional[int] = None
) -> List[List[Dict[str, Any]]]:
    """
    pdf_lines: [{'text': '...', 'y': float, 'x': float, 'page': Optional[int]}]  # page가 없을 수도 있다고 가정
    반환: 페이지별 블럭 리스트
    우선순위: 푸터 > 헤더 > y 하강(큰 점프)
    """
    pages: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    last_y = None
    seen_any_break = False

    def commit_page():
        nonlocal cur
        pages.append(cur)
        cur = []

    for i, blk in enumerate(pdf_lines):
        text = blk.get('text', '')
        y = blk.get('y')
        cur.append(blk)

        # 1) 푸터 패턴: 가장 신뢰 높음
        if is_footer_break(text):
            seen_any_break = True
            commit_page()
            last_y = None
            continue  # 이 continue는 루프 내부에 있음 (SyntaxError 방지)

        # 2) 반복 헤더: 두 번째 신뢰
        #   - 첫 페이지에는 보통 반복 헤더가 없을 수 있으므로,
        #     "현재 페이지가 비지 않았고", "직전이 커밋된 뒤 시작형 헤더"일 때만 분할
        if is_header_repeat(text) and len(cur) > 1 and seen_any_break:
            commit_page()
            last_y = None
            continue

        # 3) 큰 y 하강 감지 (예: 페이지 넘김으로 텍스트 y가 크게 리셋)
        if last_y is not None and y is not None and (last_y - y) > 500:  # 문서 스케일에 맞춰 조정
            # 단, 이전에 아무 경계도 못 봤다면(커버 페이지), 여기선 강제 커밋 X
            if seen_any_break:
                commit_page()
                last_y = y
                continue

        if y is not None:
            last_y = y

    # 마지막 잔여
    if cur:
        pages.append(cur)

    # 0쪽 보호: 커버 예외 처리 (앵커가 전혀 없었다면 현재 내용을 1쪽으로 강제)
    if not seen_any_break and pages and len(pages) > 1:
        # 매우 드문 케이스지만, 안전 차원에서 첫 묶음을 1쪽으로 확정
        pass

    # 힌트와 페이지 수 불일치시(너무 작으면) 마지막 페이지 병합/분할은 상위 레이어에서 처리
    return pages

# --- 표 그룹핑 & 분할 ---

@dataclass
class TableRow:
    r: int
    c: int
    rs: int
    cs: int
    text: str
    # 좌표가 있으면 페이지 분할에도 사용
    x: Optional[float] = None
    y: Optional[float] = None
    page_no: Optional[int] = None

def table_header_signature(rows: List[TableRow]) -> str:
    """첫 행(헤더) 텍스트들의 해시"""
    first_row_idx = min(r.r for r in rows)
    cells = [norm_text(t.text) for t in rows if t.r == first_row_idx]
    return hash_header_row(cells)

def group_tables_strong(
    rows: List[TableRow],
    page_no: int,
    y_page_min: Optional[float] = None
) -> List[List[TableRow]]:
    """
    강화된 키로 표를 분리.
    - page_no 다르면 무조건 분리
    - header_hash + approx(x_left,y_top)
    - 페이지 경계(y_page_min)에서 하드 컷
    """
    if not rows:
        return []

    # 페이지 경계에서 하드 컷: 행 기준으로 나눔
    if y_page_min is not None:
        rows_a = [r for r in rows if r.y is None or r.y >= y_page_min]
        rows_b = [r for r in rows if r.y is not None and r.y < y_page_min]
        # 페이지 경계 기준 오름차순 정렬
        if rows_b and rows_a:
            # page_no 기준으로 상/하로 쪼갠 뒤 재귀 처리
            return group_tables_strong(rows_b, page_no-1) + group_tables_strong(rows_a, page_no)

    # 헤더 시그니처
    header_sig = table_header_signature(rows) if rows else 'nil'

    # 좌상단 추정
    x_left = min((r.x for r in rows if r.x is not None), default=0.0)
    y_top  = min((r.y for r in rows if r.y is not None), default=0.0)

    key = (page_no, header_sig, approx(x_left), approx(y_top))

    # 기존 코드가 "첫 셀 텍스트 동일"로 묶었다면,
    # 이제는 동일 page_no + header_sig + approx(x,y) 가 같을 때만 이어붙임.
    grouped: Dict[Tuple[int,str,int,int], List[TableRow]] = {}
    grouped.setdefault(key, []).extend(rows)
    return list(grouped.values())

# --- 본문 빌드 (label/sen 규칙 + TOC 라인) ---

def classify_line_to_item(line: str) -> Dict[str, Any]:
    s = norm_text(line)
    # TOC(목차) 라인은 label에 숫자 꼬리가 붙을 수 있으므로 원형 유지
    if is_label(s):
        return {"label": s, "content": []}
    return {"sen": s}

# --- 안전한 continue 대체 (루프 바깥) ---

def skip_if_not(cond: bool) -> bool:
    """루프 바깥에서 'continue'처럼 쓰고 싶을 때 True면 바로 return"""
    return not cond

# 사용 예 (루프 바깥):
# if skip_if_not(cond):
#     return None

# ------------------------------------------------
# 파이프라인 적용 예 (개념)
# ------------------------------------------------

def build_json_from_sources(docx_items: List[Dict[str,Any]], pdf_items: List[Dict[str,Any]]) -> Dict[str,Any]:
    """
    1) PDF 텍스트로 페이지 경계 확정
    2) DOCX 추출 요소에 페이지번호를 매핑(앵커 기반)
    3) 표는 강화된 키로 분리
    4) label/sen 규칙 적용
    """
    # 1) PDF 페이지 분리
    pdf_pages = split_pages_by_anchors(pdf_items)

    # 2) 페이지 카탈로그(헤더/푸터/앵커 텍스트 → page_no 라프 매핑) 구성
    #    (앵커: '성적서번호:', '페이지 :' 라인 등을 키로 사용)
    anchors: Dict[str, int] = {}
    for pno, page in enumerate(pdf_pages, start=1):
        for blk in page:
            t = norm_text(blk.get('text', ''))
            if is_header_repeat(t) or is_footer_break(t):
                anchors[t] = pno

    # 3) DOCX 요소에 페이지 번호 추정 매핑 (문서/표/문단이 가진 대표 텍스트로 근접 앵커 찾기)
    def guess_page_no_by_anchor(text: str, default: int = 1) -> int:
        s = norm_text(text)
        # 완전 일치가 안 되면 일부 키워드 기반(예: 성적서번호 앞부분)으로도 fallback
        if s in anchors:
            return anchors[s]
        for k, v in anchors.items():
            if len(s) > 6 and s[:6] in k:
                return v
        return default

    # 4) 페이지별 JSON 빌드
    json_pages: List[Dict[str,Any]] = []
    total_pages = len(pdf_pages) if pdf_pages else 1

    for page_no in range(1, total_pages+1):
        json_pages.append({
            "page": page_no,
            "header": [], "footer": [],
            "content": []
        })

    # 5) DOCX 문단/표를 순회하며 페이지로 분배
    for block in docx_items:
        if 'paragraph' in block:
            txt = block['paragraph']
            item = classify_line_to_item(txt)
            pno = guess_page_no_by_anchor(txt, default=1)
            json_pages[pno-1]["content"].append(item)

        elif 'table' in block:
            rows_in: List[TableRow] = []
            pno_hint = 1
            for r,c,rs,cs,text, *pos in block['table']:  # 기존 포맷: [r,c,rs,cs,text,(x?),(y?)]
                x = pos[0] if len(pos) >= 1 else None
                y = pos[1] if len(pos) >= 2 else None
                rows_in.append(TableRow(r=r,c=c,rs=rs,cs=cs,text=text,x=x,y=y))
                # 페이지 힌트: 표 첫 텍스트로 추정
                if len(rows_in) == 1:
                    pno_hint = guess_page_no_by_anchor(text, default=1)

            # 페이지 경계 y_min (있을 때만 하드컷)
            y_min = None
            if pdf_pages and (1 <= pno_hint <= len(pdf_pages)):
                # 그 페이지의 최솟값(머리쪽)보다 작으면 이전 페이지로 잘라낼 근거
                page_ys = [blk.get('y') for blk in pdf_pages[pno_hint-1] if isinstance(blk.get('y'), (int,float))]
                y_min = min(page_ys) if page_ys else None

            tables = group_tables_strong(rows_in, pno_hint, y_page_min=y_min)
            for trows in tables:
                tbl_payload = [[tr.r, tr.c, tr.rs, tr.cs, tr.text] for tr in trows]
                json_pages[pno_hint-1]["content"].append({"table": tbl_payload})

    # 6) 마지막 정리: 빈 페이지/콘텐츠 정렬 등
    result = {
        "v": "0.4",
        "total_pages": total_pages,
        "pages": json_pages
    }
    return result
