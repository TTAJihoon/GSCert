# -*- coding: utf-8 -*-
"""
DOCX 바이트(byts) → word/document.xml 파싱 후 '시험합의서' 21개 항목 추출
- 형식 불변(본 대화의 양식) 가정
- 대표자/담당자 E-mail 충돌 방지:
  · 대표자: 라벨에 '대표자' 포함된 E-mail 라벨만 허용
  · 담당자: 라벨이 정확히 'E-mail'/'E- Mail'/'Email' 등일 때만,
           같은 행 또는 최근 N행(LOOKBACK) 안에 '담당자'가 존재해야 함,
           그리고 '대표자' 토큰이 보이면 즉시 제외
"""

from io import BytesIO
from zipfile import ZipFile
from lxml import etree
import re

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# ─────────────────────────────────────────────────────────────
# 0) 빈 결과 템플릿
# ─────────────────────────────────────────────────────────────
def _empty_process1():
    return {
        "시험신청번호": "",
        "성적서 구분": "",
        "국문명": "",
        "영문명": "",
        "사업자등록번호": "",
        "법인등록번호": "",
        "대표자": "",
        "대표자 E-Mail": "",
        "대표 전화번호": "",
        "홈페이지": "",
        "주 소": "",
        "담당자-성 명": "",
        "담당자-전화번호": "",
        "담당자-Mobile": "",
        "담당자-E- Mail": "",
        "담당자-FAX번호": "",
        "담당자-부서/직급": "",
        "국문명:": "",
        "영문명:": "",
        "제조자": "",
        "제조국가": "",
    }

# ─────────────────────────────────────────────────────────────
# 1) DOCX → word/document.xml 로드
# ─────────────────────────────────────────────────────────────
def _read_document_xml_from_docx_bytes(byts: bytes):
    with ZipFile(BytesIO(byts)) as zf:
        with zf.open("word/document.xml") as f:
            return etree.parse(f).getroot()

# ─────────────────────────────────────────────────────────────
# 2) 셀 텍스트 추출(줄바꿈/문단 보존)
# ─────────────────────────────────────────────────────────────
def _tc_text_with_newlines(tc) -> str:
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

def _all_table_rows(doc_root):
    rows = []
    for tbl in doc_root.findall(".//w:tbl", namespaces=NS):
        for tr in tbl.findall("./w:tr", namespaces=NS):
            cells = tr.findall("./w:tc", namespaces=NS)
            rows.append([_tc_text_with_newlines(tc) for tc in cells])
    return rows

# ─────────────────────────────────────────────────────────────
# 3) 라벨/토큰 매칭 유틸
# ─────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    """라벨 비교용 정규화: 소문자 + 모든 공백/개행 + 콜론 + 다양한 하이픈 제거"""
    if s is None:
        return ""
    s2 = s.lower()
    s2 = re.sub(r"[\s\u00A0]+", "", s2)
    s2 = s2.replace(":", "")
    # 하이픈/대시 계열 제거(‐-‒–—― 포함)
    s2 = re.sub(r"[-‐-‒–—―]", "", s2)
    return s2

def _has_colon(s: str) -> bool:
    return ":" in (s or "")

def _next_cell(rows, r_idx, c_idx) -> str:
    row = rows[r_idx]
    return row[c_idx + 1].strip() if (c_idx + 1 < len(row)) else ""

def _find_value_by_label(rows, label_variants, require_colon=None) -> str:
    """
    표에서 '라벨 셀'을 찾아 바로 오른쪽 셀 값을 반환.
    - label_variants: ["주 소", "주        소", "주소"] 등
    - require_colon:  None(무시) / True(라벨에 콜론 必) / False(라벨에 콜론 없어야 함)
    """
    targets = [_norm(v) for v in label_variants]
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if require_colon is True and not _has_colon(cell):
                continue
            if require_colon is False and _has_colon(cell):
                continue
            if _norm(cell) in targets:
                return _next_cell(rows, r_i, c_i)
    return ""

def _row_has_token(row, token: str) -> bool:
    tok = _norm(token)
    return any(tok in _norm(x) for x in row)

# ─────────────────────────────────────────────────────────────
# 4) 충돌 방지: 담당자 E-mail 전용 스캐너
# ─────────────────────────────────────────────────────────────
def _find_contact_email(rows, lookback: int = 2) -> str:
    """
    담당자 E-mail 추출 규칙:
      - 라벨은 정확히 'E-mail' / 'E- Mail' / 'Email' 계열만 허용(부분일치 X)
      - 같은 행 또는 최근 lookback행 내에 '담당자' 토큰이 있어야 함(블록 스코프)
      - 같은 행 또는 최근 lookback행 내에 '대표자' 토큰이 있으면 제외
    """
    label_set = {_norm("E-mail"), _norm("E- Mail"), _norm("Email")}
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if _norm(cell) in label_set:
                # 1) 대표자 토큰이 보이면 제외
                if _row_has_token(row, "대표자"):
                    continue
                bad = False
                for k in range(1, lookback + 1):
                    if r_i - k >= 0 and _row_has_token(rows[r_i - k], "대표자"):
                        bad = True
                        break
                if bad:
                    continue

                # 2) 반드시 '담당자' 맥락이어야 함
                ok = _row_has_token(row, "담당자")
                if not ok:
                    for k in range(1, lookback + 1):
                        if r_i - k >= 0 and _row_has_token(rows[r_i - k], "담당자"):
                            ok = True
                            break
                if not ok:
                    continue

                # 3) 통과 시 라벨 오른쪽 값을 반환
                return _next_cell(rows, r_i, c_i)
    return ""

# ─────────────────────────────────────────────────────────────
# 5) 항목별 규칙
# ─────────────────────────────────────────────────────────────
def _detect_score_type(rows) -> str:
    """성적서 구분: 'TTA 성적서 (V/√/✔/✓)' / 'KOLAS 성적서 (…)' 중 체크된 항목"""
    mark = r"[Vv√✔✓]"
    for row in rows:
        joined = " ".join(row)
        if ("TTA 성적서" in joined) and ("KOLAS 성적서" in joined):
            s = re.sub(r"\s+", " ", joined)
            tta = re.search(r"TTA\s*성적서\s*\(\s*(" + mark + r")\s*\)", s)
            kol = re.search(r"KOLAS\s*성적서\s*\(\s*(" + mark + r")\s*\)", s)
            if tta and tta.group(1):
                return "TTA 성적서"
            if kol and kol.group(1):
                return "KOLAS 성적서"
    return ""

def _extract_company_kr_en(rows):
    """
    신청기업(기관)명 블록:
    - 라벨 '국문명' / '영문명' (콜론 없음) 셀이 있고, 바로 오른쪽 셀에 값이 들어있는 구조.
    """
    kr = en = ""
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            cell_n = _norm(cell)
            if cell_n == _norm("국문명") and not _has_colon(cell):
                kr = kr or _next_cell(rows, r_i, c_i)
            if cell_n == _norm("영문명") and not _has_colon(cell):
                en = en or _next_cell(rows, r_i, c_i)
    return kr, en

def _extract_product_names(rows):
    """
    제품명 및 버전 블록:
    - (A) '제품명 및 버전' 라벨 다음 '값 셀' 안에서 '국문명:' / '영문명:' 추출
    - (B) 라벨 셀 자체가 '국문명:' / '영문명:'인 경우
    - (C) 보강: 표의 '모든 셀'에서 라벨+값 패턴을 스캔 (병합/행분리 대비)
    """
    kr = en = ""

    # (A) '제품명 및 버전' → 다음 셀 텍스트 안에서 추출
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if "제품명 및 버전" in cell:
                val = _next_cell(rows, r_i, c_i)
                if val:
                    m_kr = re.search(r"(?:^|\n)\s*국문명\s*:\s*([^\n]+)", val)
                    m_en = re.search(r"(?:^|\n)\s*영문명\s*:\s*([^\n]+)", val)
                    if m_kr and not kr:
                        kr = m_kr.group(1).strip()
                    if m_en and not en:
                        en = m_en.group(1).strip()

    # (B) 라벨 셀 자체가 '국문명:' / '영문명:'인 레이아웃
    if not kr:
        kr = _find_value_by_label(rows, ["국문명:"], require_colon=True)
    if not en:
        en = _find_value_by_label(rows, ["영문명:"], require_colon=True)

    # (C) 최종 보강: 표의 모든 셀을 스캔 (값셀 내부에 라벨이 있는 경우)
    if not kr or not en:
        for row in rows:
            for cell in row:
                if not kr:
                    m_kr = re.search(r"(?:^|\n)\s*국문명\s*:\s*([^\n]+)", cell)
                    if m_kr:
                        kr = m_kr.group(1).strip()
                if not en:
                    m_en = re.search(r"(?:^|\n)\s*영문명\s*:\s*([^\n]+)", cell)
                    if m_en:
                        en = m_en.group(1).strip()
                if kr and en:
                    break
            if kr and en:
                break

    return kr, en

# ─────────────────────────────────────────────────────────────
# 6) 메인: 합의서 파서 (byts, filename) → out
# ─────────────────────────────────────────────────────────────
def extract_process1_docx_basic(byts: bytes, filename: str):
    """
    Parameters
    ----------
    byts : bytes
        .docx 파일 바이트
    filename : str
        파일명(로그/디버깅 용도; 파싱엔 미사용)

    Returns
    -------
    out : dict
        지정된 21개 키를 갖는 결과 딕셔너리
    """
    out = _empty_process1()

    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception:
        return out  # 손상 파일 등 예외 시 빈 결과

    rows = _all_table_rows(doc_root)

    # 1) 시험신청번호
    out["시험신청번호"] = _find_value_by_label(rows, ["시험신청번호"])

    # 2) 성적서 구분
    out["성적서 구분"] = _detect_score_type(rows)

    # 3) 4) 신청기업(기관)명 - 국/영문 (콜론 없음)
    kr_company, en_company = _extract_company_kr_en(rows)
    out["국문명"] = kr_company
    out["영문명"] = en_company

    # 5) ~ 11)
    out["사업자등록번호"] = _find_value_by_label(rows, ["사업자등록번호", "사업자 등록번호"])
    out["법인등록번호"]   = _find_value_by_label(rows, ["법인등록번호", "법인 등록번호"])
    out["대표자"]         = _find_value_by_label(rows, ["대표자"])
    out["대표자 E-Mail"]  = _find_value_by_label(rows, ["대표자 E-mail", "대표자 E- Mail", "대표자 E-Mail", "대표자 이메일"])
    out["대표 전화번호"]   = _find_value_by_label(rows, ["대표 전화번호", "대표전화번호", "대표전화"])
    out["홈페이지"]       = _find_value_by_label(rows, ["홈페이지", "Website", "웹사이트"])
    out["주 소"]          = _find_value_by_label(rows, ["주        소", "주 소", "주소"])

    # 12) ~ 17) (담당자)
    out["담당자-성 명"]    = _find_value_by_label(rows, ["성   명", "성 명"])
    out["담당자-전화번호"]  = _find_value_by_label(rows, ["전화번호", "담당자 전화번호"])
    out["담당자-Mobile"]   = _find_value_by_label(rows, ["Mobile", "모바일"])

    # ★ 충돌 방지 로직 적용(담당자 E-mail)
    out["담당자-E- Mail"]  = _find_contact_email(rows)

    out["담당자-FAX번호"]   = _find_value_by_label(rows, ["FAX번호", "팩스번호", "FAX 번호"])
    out["담당자-부서/직급"]  = _find_value_by_label(rows, ["부서/직급", "부서 / 직급", "부서", "직급"])

    # 18) 19) (제품명 및 버전 - 콜론 있음)
    kr_prod, en_prod = _extract_product_names(rows)
    out["국문명:"] = kr_prod
    out["영문명:"] = en_prod

    # 20) 21)
    out["제조자"]   = _find_value_by_label(rows, ["제조자"])
    out["제조국가"] = _find_value_by_label(rows, ["제조국가"])

    return out
