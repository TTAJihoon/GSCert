# -*- coding: utf-8 -*-

from io import BytesIO
from zipfile import ZipFile
from lxml import etree
import re
import sqlite3
import os

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# ─────────────────────────────────────────────────────────────
# 0) 빈 결과 템플릿 (신청유형/재인증 여부/재인증 정보 포함)
# ─────────────────────────────────────────────────────────────
def _empty_process1():
    return {
        "시험신청번호": "",
        "성적서 구분": "",
        "신청유형": "",
        "재인증 여부": "",   # 재인증: "O", 신규인증: "X", 그 외: ""
        "재인증 정보": "-",  # 재인증 아닐 때는 "-"
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
    text = _re.sub(r"[ \t]+", " ", text)
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
                if _row_has_token(row, "대표자"):
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

# ─────────────────────────────────────────────────────────────
# 체크형 필드 탐지
# ─────────────────────────────────────────────────────────────
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

def _detect_cert_apply_type(rows) -> str:
    """한 행에 '신규인증(...)'과 '재인증(...)'이 함께 있고 괄호 안에 체크가 있는 경우만 판정"""
    mark = r"[Vv√✔✓]"
    for row in rows:
        joined = " ".join(row)
        if ("신규인증" in joined) and ("재인증" in joined):
            s = re.sub(r"\s+", " ", joined)
            new_mark = re.search(r"신규인증\s*\(\s*(" + mark + r")\s*\)", s)
            re_mark  = re.search(r"재인증\s*\(\s*(" + mark + r")\s*\)", s)
            if re_mark and re_mark.group(1):
                return "재인증"
            if new_mark and new_mark.group(1):
                return "신규인증"
    return ""

# ─────────────────────────────────────────────────────────────
# 재인증 전용 헬퍼 (리팩토링 포인트)
# ─────────────────────────────────────────────────────────────
def _recert_find_body_text(rows) -> str:
    """'재인증 신청 시 기재사항'을 포함하는 셀의 다음 줄부터 끝까지 텍스트 반환. 없으면 ''."""
    for row in rows:
        for cell in row:
            if "재인증 신청 시 기재사항" in cell:
                lines = cell.splitlines()
                for i, ln in enumerate(lines):
                    if "재인증 신청 시 기재사항" in ln:
                        return "\n".join(lines[i+1:]).strip()
                return ""  # 문구는 있었으나 다음 줄이 없는 경우
    return ""

def _recert_parse_cert_no(text: str) -> str:
    """본문에서 '기 인증번호:' 뒤의 값을 한 줄 범위에서 추출."""
    m = re.search(r"기\s*인증번호\s*:\s*([^\n\r]+)", text or "")
    return m.group(1).strip() if m else ""

def _recert_fetch_total_wd(cert_no: str, db_path: str) -> str:
    """main/data/reference.db에서 인증번호=cert_no의 '총WD' 조회. 실패/미발견 시 ''."""
    if not cert_no:
        return ""
    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        return ""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        tbls = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        target = None
        for (tname,) in tbls:
            cols = cur.execute(f"PRAGMA table_info('{tname}')").fetchall()
            colnames = {c[1] for c in cols}
            if "인증번호" in colnames and "총WD" in colnames:
                target = tname
                break
        if not target:
            return ""
        row = cur.execute(
            f"SELECT \"총WD\" FROM \"{target}\" WHERE \"인증번호\"=? LIMIT 1",
            (cert_no,),
        ).fetchone()
        return "" if not row or row[0] is None else str(row[0])
    except Exception:
        return ""
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass

def _build_recert_info(rows, db_path: str = os.path.join("main", "data", "reference.db")) -> str:
    """
    재인증일 때만 호출하도록 설계.
    - 본문 텍스트 추출 → 인증번호 파싱 → WD 조회 → 결합 문자열 반환
    - 본문 없으면 "-"
    """
    body = _recert_find_body_text(rows)
    if not body:
        return "-"
    cert_no = _recert_parse_cert_no(body)
    wd = _recert_fetch_total_wd(cert_no, db_path) if cert_no else ""
    return f"{body}\n기 인증 제품 WD: {wd}"

# ─────────────────────────────────────────────────────────────
# 메인(1): 합의서 파서 (신청유형/재인증 여부/재인증 정보 포함)
# ─────────────────────────────────────────────────────────────
def extract_process1_docx_basic(byts: bytes, filename: str):
    out = _empty_process1()
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception as e:
        print(f"[print_out error] {e}")
        return out

    rows = _all_table_rows(doc_root)

    out["시험신청번호"] = _find_value_by_label(rows, ["시험신청번호"])
    out["성적서 구분"] = _detect_score_type(rows)

    cert_type = _detect_cert_apply_type(rows)
    out["신청유형"] = cert_type
    out["재인증 여부"] = "O" if cert_type == "재인증" else ("X" if cert_type == "신규인증" else "")
    out["재인증 정보"] = _build_recert_info(rows) if cert_type == "재인증" else "-"

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
    _print_out(out)
    return out

def _print_out(out: dict) -> None:
    """out의 키/값을 순서대로 모두 출력."""
    try:
        print("=== extract_process1_docx_basic: 결과 out ===")
        for k, v in out.items():   # 파이썬3.7+ dict는 삽입 순서 보존
            print(f"{k}: {v}")
        print("=== end of out ===")
    except Exception as e:
        print(f"[print_out error] {e}")
        
# ─────────────────────────────────────────────────────────────
# 메인(2): 재인증 본문+WD (이전 시그니처 유지, 내부는 리팩토링 헬퍼 재사용)
# ─────────────────────────────────────────────────────────────
def extract_recert_text_and_wd(byts: bytes, filename: str) -> str:
    try:
        doc_root = _read_document_xml_from_docx_bytes(byts)
    except Exception as e:
        print(f"[print_out error] {e}")
        return "-"

    rows = _all_table_rows(doc_root)
    cert_type = _detect_cert_apply_type(rows)
    if cert_type != "재인증":
        return "-"

    return _build_recert_info(rows)
