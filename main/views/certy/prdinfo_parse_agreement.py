# -*- coding: utf-8 -*-
"""
DOCX 바이트(byts) → word/document.xml 파싱 후 '시험합의서' 항목 추출 + 재인증 부가정보
- 기존 21개 항목 추출 로직 유지
- 추가:
  1) _detect_cert_apply_type(rows): '신규인증/재인증' 중 체크(V/√/✔/✓)된 항목 탐지
  2) extract_recert_text_and_wd(byts, filename): 재인증 시 '※ 재인증 신청 시 기재사항' 셀 하단 텍스트(변수1) 추출,
     '기 인증번호:' 값을 변수2로 파싱, reference.db에서 해당 인증번호의 '총WD'(변수3) 조회 후
     '{변수1}\n기 인증 제품 WD: {변수3}' 반환. 신규인증이면 "-" 반환.
"""

from io import BytesIO
from zipfile import ZipFile
from lxml import etree
import re
import sqlite3
import os

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# ─────────────────────────────────────────────────────────────
# 0) 빈 결과 템플릿 (기존)
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

def _read_document_xml_from_docx_bytes(byts: bytes):
    with ZipFile(BytesIO(byts)) as zf:
        with zf.open("word/document.xml") as f:
            return etree.parse(f).getroot()

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
    import re as _re
    text = "\n".join(parts)
    text = _re.sub(r"[ \t]+", " ", text)  # 줄바꿈 유지, 연속 공백 정규화
    return text.strip()

def _all_table_rows(doc_root):
    rows = []
    for tbl in doc_root.findall(".//w:tbl", namespaces=NS):
        for tr in tbl.findall("./w:tr", namespaces=NS):
            cells = tr.findall("./w:tc", namespaces=NS)
            rows.append([_tc_text_with_newlines(tc) for tc in cells])
    return rows

def _norm(s: str) -> str:
    if s is None: return ""
    s2 = s.lower()
    s2 = re.sub(r"[\s\u00A0]+", "", s2)
    s2 = s2.replace(":", "")
    s2 = re.sub(r"[-‐-‒–—―]", "", s2)
    return s2

def _has_colon(s: str) -> bool:
    return ":" in (s or "")

def _next_cell(rows, r_idx, c_idx) -> str:
    row = rows[r_idx]
    return row[c_idx + 1].strip() if (c_idx + 1 < len(row)) else ""

def _find_value_by_label(rows, label_variants, require_colon=None) -> str:
    targets = [_norm(v) for v in label_variants]
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if require_colon is True and not _has_colon(cell):   continue
            if require_colon is False and _has_colon(cell):      continue
            if _norm(cell) in targets:
                return _next_cell(rows, r_i, c_i)
    return ""

def _row_has_token(row, token: str) -> bool:
    tok = _norm(token)
    return any(tok in _norm(x) for x in row)

def _find_contact_email(rows, lookback: int = 2) -> str:
    label_set = {_norm("E-mail"), _norm("E- Mail"), _norm("Email")}
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if _norm(cell) in label_set:
                if _row_has_token(row, "대표자"):  # 대표자 맥락 제외
                    continue
                bad = False
                for k in range(1, lookback + 1):
                    if r_i - k >= 0 and _row_has_token(rows[r_i - k], "대표자"):
                        bad = True; break
                if bad: continue
                ok = _row_has_token(row, "담당자")
                if not ok:
                    for k in range(1, lookback + 1):
                        if r_i - k >= 0 and _row_has_token(rows[r_i - k], "담당자"):
                            ok = True; break
                if not ok: continue
                return _next_cell(rows, r_i, c_i)
    return ""

# 기존: 성적서(TTA/KOLAS) 구분
def _detect_score_type(rows) -> str:
    mark = r"[Vv√✔✓]"
    for row in rows:
        joined = " ".join(row)
        if ("TTA 성적서" in joined) and ("KOLAS 성적서" in joined):
            s = re.sub(r"\s+", " ", joined)
            tta = re.search(r"TTA\s*성적서\s*\(\s*(" + mark + r")\s*\)", s)
            kol = re.search(r"KOLAS\s*성적서\s*\(\s*(" + mark + r")\s*\)", s)
            if tta and tta.group(1): return "TTA 성적서"
            if kol and kol.group(1): return "KOLAS 성적서"
    return ""

# 신규 추가: 신청 유형(신규인증/재인증) 체크 탐지
def _detect_cert_apply_type(rows) -> str:
    """
    표의 한 행/셀에 '신규인증( V )', '재인증( V )' 둘 다 나타나는 형태를 가정.
    체크 마크는 V/v/√/✔/✓ 허용.
    """
    mark = r"[Vv√✔✓]"
    for row in rows:
        joined = " ".join(row)
        s = re.sub(r"\s+", " ", joined)
        m_new = re.search(r"신규\s*인증|신규인증", s)
        m_re  = re.search(r"재\s*인증|재인증", s)
        if m_new or m_re:
            new_mark = re.search(r"신규\s*인증|신규인증.*?\(\s*(" + mark + r")\s*\)", s)
            re_mark  = re.search(r"재\s*인증|재인증.*?\(\s*(" + mark + r")\s*\)", s)
            # 좀 더 강건하게: 두 구문 각각 다시 정규식
            new_mark = re.search(r"신규\s*인증|신규인증\s*\(\s*(" + mark + r")\s*\)", s) or \
                       re.search(r"신규인증\s*\(\s*(" + mark + r")\s*\)", s)
            re_mark  = re.search(r"재\s*인증|재인증\s*\(\s*(" + mark + r")\s*\)", s) or \
                       re.search(r"재인증\s*\(\s*(" + mark + r")\s*\)", s)
            if re_mark and re_mark.group(0):
                return "재인증"
            if new_mark and new_mark.group(0):
                return "신규인증"
    return ""

def _extract_company_kr_en(rows):
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
    kr = en = ""
    for r_i, row in enumerate(rows):
        for c_i, cell in enumerate(row):
            if "제품명 및 버전" in cell:
                val = _next_cell(rows, r_i, c_i)
                if val:
                    m_kr = re.search(r"(?:^|\n)\s*국문명\s*:\s*([^\n]+)", val)
                    m_en = re.search(r"(?:^|\n)\s*영문명\s*:\s*([^\n]+)", val)
                    if m_kr and not kr: kr = m_kr.group(1).strip()
                    if m_en and not en: en = m_en.group(1).strip()
    if not kr:
        kr = _find_value_by_label(rows, ["국문명:"], require_colon=True)
    if not en:
        en = _find_value_by_label(rows, ["영문명:"], require_colon=True)
    if not kr or not en:
        for row in rows:
            for cell in row:
                if not kr:
                    m_kr = re.search(r"(?:^|\n)\s*국문명\s*:\s*([^\n]+)", cell)
                    if m_kr: kr = m_kr.group(1).strip()
                if not en:
                    m_en = re.search(r"(?:^|\n)\s*영문명\s*:\s*([^\n]+)", cell)
                    if m_en: en = m_en.group(1).strip()
                if kr and en: break
            if kr and en: break
    return kr, en

# ─────────────────────────────────────────────────────────────
# 메인(기존): 합의서 파서
# ─────────────────────────────────────────────────────────────
def extract_process1_docx_basic(byts: bytes, filename: str):
    out = _empty_process1()
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception:
        return out

    rows = _all_table_rows(doc_root)

    out["시험신청번호"] = _find_value_by_label(rows, ["시험신청번호"])
    out["성적서 구분"] = _detect_score_type(rows)

    # 신청 유형(신규인증/재인증)도 함께 추가로 리턴(호환성 위해 새 키로 추가)
    out["신청유형"] = _detect_cert_apply_type(rows)  # ← 신규 추가

    kr_company, en_company = _extract_company_kr_en(rows)
    out["국문명"] = kr_company
    out["영문명"] = en_company

    out["사업자등록번호"] = _find_value_by_label(rows, ["사업자등록번호", "사업자 등록번호"])
    out["법인등록번호"]   = _find_value_by_label(rows, ["법인등록번호", "법인 등록번호"])
    out["대표자"]         = _find_value_by_label(rows, ["대표자"])
    out["대표자 E-Mail"]  = _find_value_by_label(rows, ["대표자 E-mail", "대표자 E- Mail", "대표자 E-Mail", "대표자 이메일"])
    out["대표 전화번호"]   = _find_value_by_label(rows, ["대표 전화번호", "대표전화번호", "대표전화"])
    out["홈페이지"]       = _find_value_by_label(rows, ["홈페이지", "Website", "웹사이트"])
    out["주 소"]          = _find_value_by_label(rows, ["주        소", "주 소", "주소"])

    out["담당자-성 명"]    = _find_value_by_label(rows, ["성   명", "성 명"])
    out["담당자-전화번호"]  = _find_value_by_label(rows, ["전화번호", "담당자 전화번호"])
    out["담당자-Mobile"]   = _find_value_by_label(rows, ["Mobile", "모바일"])
    out["담당자-E- Mail"]  = _find_contact_email(rows)
    out["담당자-FAX번호"]   = _find_value_by_label(rows, ["FAX번호", "팩스번호", "FAX 번호"])
    out["담당자-부서/직급"]  = _find_value_by_label(rows, ["부서/직급", "부서 / 직급", "부서", "직급"])

    kr_prod, en_prod = _extract_product_names(rows)
    out["국문명:"] = kr_prod
    out["영문명:"] = en_prod

    out["제조자"]   = _find_value_by_label(rows, ["제조자"])
    out["제조국가"] = _find_value_by_label(rows, ["제조국가"])
    return out

# ─────────────────────────────────────────────────────────────
# 신규: 재인증 기재사항 텍스트 + '기 인증 제품 WD' 조회
# ─────────────────────────────────────────────────────────────
def extract_recert_text_and_wd(byts: bytes, filename: str) -> str:
    """
    반환:
      - '신규인증' 체크 시: "-"
      - '재인증' 체크 시:
        변수1 = '※ 재인증 신청 시 기재사항'이 포함된 '해당 셀'의 **다음 줄부터** 끝까지(좌우 공백/양끝 줄바꿈 제거)
        변수2 = 변수1에서 '기 인증번호:' 뒤 값
        변수3 = sqlite(main/data/reference.db)에서 인증번호=변수2 인 행의 '총WD'
        return f"{변수1}\n기 인증 제품 WD: {변수3}"
    """
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception:
        return "-"

    rows = _all_table_rows(doc_root)
    cert_type = _detect_cert_apply_type(rows)
    if cert_type != "재인증":
        return "-"  # 명세 1-6

    # '※ 재인증 신청 시 기재사항' 문구가 들어있는 '셀'을 찾아 그 '셀'의 아래 줄부터 수집
    target = None
    for row in rows:
        for cell in row:
            if "재인증 신청 시 기재사항" in cell:
                target = cell
                break
        if target: break
    if not target:
        return "-"

    # 셀 내에서 '문구가 있는 그 줄' 다음 줄부터 끝까지
    lines = target.splitlines()
    idx = -1
    for i, ln in enumerate(lines):
        if "재인증 신청 시 기재사항" in ln:
            idx = i; break
    text_after = "\n".join(lines[idx+1:]) if idx >= 0 else ""
    var1 = text_after.strip()  # 양끝만 정리(내부 공백/줄바꿈 유지)

    # 변수2: '기 인증번호:' 뒤의 값
    m = re.search(r"기\s*인증번호\s*:\s*([^\n\r]+)", var1)
    var2 = m.group(1).strip() if m else ""

    # 변수3: reference.db 조회(테이블 미지정 → '인증번호'와 '총WD' 컬럼을 가진 테이블 자동 탐색)
    var3 = ""
    db_path_candidates = [
        os.path.join("main", "data", "reference.db"),
        os.path.join(os.path.dirname(__file__), "..", "data", "reference.db"),
        os.path.join(os.getcwd(), "main", "data", "reference.db"),
    ]
    db_path = next((p for p in db_path_candidates if os.path.exists(os.path.abspath(p))), None)
    if db_path and var2:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            # '인증번호' & '총WD'가 있는 테이블 자동 탐색
            tbls = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_name = None
            for (tname,) in tbls:
                cols = cur.execute(f"PRAGMA table_info('{tname}')").fetchall()
                colnames = {c[1] for c in cols}
                if "인증번호" in colnames and "총WD" in colnames:
                    table_name = tname
                    break
            if table_name:
                row = cur.execute(
                    f"SELECT \"총WD\" FROM \"{table_name}\" WHERE \"인증번호\"=? LIMIT 1", (var2,)
                ).fetchone()
                if row and row[0] is not None:
                    var3 = str(row[0])
        except Exception:
            var3 = ""
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return f"{var1}\n기 인증 제품 WD: {var3}" if var1 else "-"
