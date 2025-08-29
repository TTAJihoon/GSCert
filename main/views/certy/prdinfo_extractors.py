# prdinfo_extractors.py
import re
from collections import defaultdict
from docx import Document
from openpyxl import load_workbook

# ─────────────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────────────

def normalize_spaces(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\u200b", " ").replace("\xa0", " ")).strip()

def flat(s: str) -> str:
    return re.sub(r"\s+", "", normalize_spaces(s))

def text_lines_from_docx(doc: Document):
    lines = []
    for p in doc.paragraphs:
        t = normalize_spaces(p.text)
        if t:
            lines.append(t)
    for tbl in doc.tables:
        for row in tbl.rows:
            row_texts = [normalize_spaces(c.text) for c in row.cells]
            for t in row_texts:
                if t:
                    for sub in [normalize_spaces(x) for x in re.split(r"[\r\n]+", t) if normalize_spaces(x)]:
                        lines.append(sub)
            for i in range(0, len(row_texts)-1):
                l, v = row_texts[i], row_texts[i+1]
                if l or v:
                    lines.append(f"{l} : {v}".strip(" :"))
    return lines

def find_label_value_in_tables(doc: Document, label_patterns):
    found = {}
    for tbl in doc.tables:
        for row in tbl.rows:
            texts = [normalize_spaces(c.text) for c in row.cells]
            # 한 셀 내 '라벨: 값'
            for t in texts:
                for key, creg in label_patterns.items():
                    if creg.search(t):
                        m = re.split(r"[:：]\s*", t, maxsplit=1)
                        if len(m) == 2 and normalize_spaces(m[1]):
                            found.setdefault(key, normalize_spaces(m[1]))
            # 인접 우측 셀
            for i in range(0, len(texts)-1):
                l, v = texts[i], texts[i+1]
                for key, creg in label_patterns.items():
                    if creg.search(l) and normalize_spaces(v):
                        found.setdefault(key, normalize_spaces(v))
    return found

# ─────────────────────────────────────────────────────
# 1번 과정: .docx 기본정보 추출
# ─────────────────────────────────────────────────────

_1_LABELS_REGEX = {
    "국문명": re.compile(r"\b국문명\b", re.I),        # 기업/기관(콜론 無)
    "영문명": re.compile(r"\b영문명\b", re.I),
    "국문명:": re.compile(r"\b국문명\s*:\b"),         # 제품(콜론 有)
    "영문명:": re.compile(r"\b영문명\s*:\b"),
    "사업자등록번호": re.compile(r"사업자\s*등록\s*번호", re.I),
    "법인등록번호": re.compile(r"법인\s*등록\s*번호", re.I),
    "대표자": re.compile(r"\b대표자\b"),
    "대표자 E- Mail": re.compile(r"대표자\s*E-?\s*Mail", re.I),
    "대표자 E-Mail": re.compile(r"대표자\s*E-?\s*Mail", re.I),
    "대표 전화번호": re.compile(r"대표\s*전화\s*번호", re.I),
    "홈페이지": re.compile(r"\b홈페이지\b", re.I),
    "주 소": re.compile(r"주\s*소", re.I),
    "담당자-성 명": re.compile(r"담당자\s*-\s*성\s*명|담당자\s*성명", re.I),
    "담당자-전화번호": re.compile(r"담당자\s*-\s*전화\s*번호|담당자\s*전화번호", re.I),
    "담당자-Mobile": re.compile(r"담당자\s*-\s*Mobile|담당자\s*휴대전화|담당자\s*핸드폰", re.I),
    "담당자-E- Mail": re.compile(r"담당자\s*-\s*E-?\s*Mail|담당자\s*이메일", re.I),
    "담당자-FAX번호": re.compile(r"담당자\s*-\s*FAX\s*번호|담당자\s*팩스", re.I),
    "담당자-부서/직급": re.compile(r"담당자\s*-\s*부서\s*/\s*직급|담당자\s*부서\s*/\s*직급|담당자\s*부서|담당자\s*직급", re.I),
    "제조자": re.compile(r"\b제조자\b"),
    "제조국가": re.compile(r"\b제조\s*국가\b"),
    "시험신청번호": re.compile(r"\b시험\s*신청\s*번호\b"),
}

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

def extract_process1_docx_basic(byts, filename):
    doc = Document(byts)
    raw_lines = text_lines_from_docx(doc)
    if not raw_lines:
        return _empty_process1()

    found = find_label_value_in_tables(doc, _1_LABELS_REGEX)

    # 본문 '라벨: 값' 보조 추출
    for line in raw_lines:
        t = normalize_spaces(line)
        for key, creg in _1_LABELS_REGEX.items():
            if creg.search(t):
                m = re.split(r"[:：]\s*", t, maxsplit=1)
                if len(m) == 2 and normalize_spaces(m[1]):
                    found.setdefault(key, normalize_spaces(m[1]))

    # 시험신청번호 보정
    if "시험신청번호" not in found:
        for line in raw_lines:
            m = re.search(r"(시험\s*신청\s*번호)\s*[:：]?\s*([A-Za-z0-9\-\_]+)", line)
            if m:
                found["시험신청번호"] = normalize_spaces(m.group(2))
                break

    # 성적서 구분(체크마크)
    score_kind = ""
    MARK = r"(V|√|✔|✓)"
    for line in raw_lines:
        L = normalize_spaces(line)
        if re.search(r"TTA\s*성적서", L, re.I) and re.search(MARK, L):
            score_kind = "TTA 성적서"
        if re.search(r"KOLAS\s*성적서", L, re.I) and re.search(MARK, L):
            score_kind = "KOLAS 성적서"

    out = _empty_process1()
    out.update({
        "시험신청번호": found.get("시험신청번호", ""),
        "성적서 구분": score_kind,
        "국문명": found.get("국문명", ""),
        "영문명": found.get("영문명", ""),  # ✅ 버그 수정: 함수호출이 아니라 .get()
        "사업자등록번호": found.get("사업자등록번호", ""),
        "법인등록번호": found.get("법인등록번호", ""),
        "대표자": found.get("대표자", ""),
        "대표자 E-Mail": found.get("대표자 E- Mail", "") or found.get("대표자 E-Mail", ""),
        "대표 전화번호": found.get("대표 전화번호", ""),
        "홈페이지": found.get("홈페이지", ""),
        "주 소": found.get("주 소", ""),
        "담당자-성 명": found.get("담당자-성 명", ""),
        "담당자-전화번호": found.get("담당자-전화번호", ""),
        "담당자-Mobile": found.get("담당자-Mobile", ""),
        "담당자-E- Mail": found.get("담당자-E- Mail", ""),
        "담당자-FAX번호": found.get("담당자-FAX번호", ""),
        "담당자-부서/직급": found.get("담당자-부서/직급", ""),
        "국문명:": found.get("국문명:", ""),
        "영문명:": found.get("영문명:", ""),
        "제조자": found.get("제조자", ""),
        "제조국가": found.get("제조국가", ""),
    })
    return out

# ─────────────────────────────────────────────────────
# 2번 과정: .docx 개요/기간/소요일수
# ─────────────────────────────────────────────────────

_DATE_PATTERNS = [
    re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일"),
    re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}"),
    re.compile(r"\b\d{1,2}/\d{1,2}\b"),
]

def extract_process2_docx_overview(byts, filename):
    doc = Document(byts)
    lines = text_lines_from_docx(doc)
    if not lines:
        return {
            "시험기간": [],
            "개요 및 특성(설명)": "",
            "개요 및 특성(주요 기능)": [],
            "소요일수": 0,
            "파일명": filename,
        }

    # ── (강화) "6. 시험기간" 블록에서 기간 직접 추출
    start_idx, end_idx = 0, len(lines)
    for i, t in enumerate(lines):
        if re.search(r"6[.)]?\s*시험기간", t):
            start_idx = i
            break
    for i, t in enumerate(lines[start_idx:], start=start_idx):
        if re.search(r"7[.)]?\s*시험방법", t):
            end_idx = i
            break

    block_text = " ".join(lines[start_idx:end_idx])
    period_pat = re.compile(
        r"(?:\((?P<label>[^)]+)\)\s*)?"
        r"(?P<start>\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}\.\d{1,2}\.\d{1,2})"
        r"\s*[~\-]\s*"
        r"(?P<end>\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}\.\d{1,2}\.\d{1,2})"
    )
    exam_periods = []
    for m in period_pat.finditer(block_text):
        label = normalize_spaces(m.group("label") or "")
        s, e = normalize_spaces(m.group("start")), normalize_spaces(m.group("end"))
        line = f"({label}) {s} ~ {e}" if label else f"{s} ~ {e}"
        if line not in exam_periods:
            exam_periods.append(line)

    # (폴백) 기존 방식: “7. 시험방법” 전 영역에서 날짜 들어간 줄 모으기
    if not exam_periods:
        cap_lines = []
        upper_idx = end_idx
        for t in lines[:upper_idx]:
            if any(p.search(t) for p in _DATE_PATTERNS):
                cap_lines.append(normalize_spaces(t))
        seen = set()
        for t in cap_lines:
            if t not in seen:
                exam_periods.append(t); seen.add(t)

    # 개요/주요 기능
    whole = " ".join(lines)
    desc = ""
    m = re.search(r"본\s*제품은(.*?)(?:으로\s*주요\s*기능은\s*다음과\s*같다)", whole)
    if m:
        desc = normalize_spaces(m.group(1))

    feats = []
    m2 = re.search(r"다음과\s*같다[^\S\r\n]*[:：]?(.*?)(?:※\s*상세기능은|$)", whole, re.S)
    if m2:
        block = normalize_spaces(m2.group(1))
        for seg in re.split(r"[•\-\∙\·\u2219;]|[\r\n]+", block):
            s = normalize_spaces(seg)
            if s:
                feats.append(s)

    # 소요일수(표의 해당 열 합계)
    total_days = 0
    for tbl in doc.tables:
        header_idx = None
        days_col = None
        for r, row in enumerate(tbl.rows):
            cells = [normalize_spaces(c.text) for c in row.cells]
            if any("소요일수" in x for x in cells):
                header_idx = r
                for c_idx, txt in enumerate(cells):
                    if "소요일수" in txt:
                        days_col = c_idx
                        break
                break
        if header_idx is not None and days_col is not None:
            for row in tbl.rows[header_idx+1:]:
                t = normalize_spaces(row.cells[days_col].text)
                t = re.sub(r"[^\d]", "", t)
                if t.isdigit():
                    total_days += int(t)

    return {
        "시험기간": exam_periods,
        "개요 및 특성(설명)": desc,
        "개요 및 특성(주요 기능)": feats,
        "소요일수": total_days,
        "파일명": filename,
    }

# ─────────────────────────────────────────────────────
# 3번 과정: .xlsx 결함 집계
# ─────────────────────────────────────────────────────

QUAL_LABEL_MAP = {
    "적합성": ["기능적합성"],
    "효율성": ["성능효율성"],
    "호환성": ["호환성"],
    "사용성": ["사용성"],
    "신뢰성": ["신뢰성"],
    "보안성": ["보안성"],
    "유지보수성": ["유지보수성"],
    "이식성": ["이식성"],
    "요구사항": ["일반적요구사항"],
}
DEG_LABELS = ["High", "Medium", "Low"]

def _to_int(s):
    s = normalize_spaces(s)
    if not s:
        return 0
    s = re.sub(r"[^\d\-]", "", s)
    try:
        return int(s)
    except Exception:
        return 0

def _defect_round_from_filename(name: str) -> int:
    m = re.search(r"v(\d+)(?:\.\d+)?", name or "", re.I)
    return int(m.group(1)) if m else 0

def extract_process3_xlsx_defects(byts, filename):
    wb = load_workbook(byts, data_only=True)
    sh = wb["시험분석자료"] if "시험분석자료" in wb.sheetnames else None

    out = {
        "결함차수": _defect_round_from_filename(filename),
        "적합성": {"수정전": 0, "최종": 0},
        "효율성": {"수정전": 0, "최종": 0},
        "호환성": {"수정전": 0, "최종": 0},
        "사용성": {"수정전": 0, "최종": 0},
        "신뢰성": {"수정전": 0, "최종": 0},
        "보안성": {"수정전": 0, "최종": 0},
        "유지보수성": {"수정전": 0, "최종": 0},
        "이식성": {"수정전": 0, "최종": 0},
        "요구사항": {"수정전": 0, "최종": 0},
        "High": {"수정전": 0, "최종": 0},
        "Medium": {"수정전": 0, "최종": 0},
        "Low": {"수정전": 0, "최종": 0},
    }
    if sh is None:
        return out

    values = [[(cell.value if cell.value is not None else "") for cell in row] for row in sh.iter_rows()]
    H, W = len(values), max((len(r) for r in values), default=0)

    def txt(r, c):
        try:
            return normalize_spaces(values[r][c])
        except Exception:
            return ""

    def find_header_cols(start_r):
        for r in range(start_r, min(start_r+5, H)):
            row = [txt(r, c) for c in range(W)]
            try:
                pre_idx = next(i for i, v in enumerate(row) if "수정전" in v)
                fin_idx = next(i for i, v in enumerate(row) if "최종" in v)
                return r, pre_idx, fin_idx
            except StopIteration:
                continue
        return None

    # 블록 A: 품질특성별 결함내역
    startA = None
    for r in range(H):
        line = "".join(txt(r, c) for c in range(W))
        if "품질" in line and "특성" in line and "결함" in line:
            startA = r
            break
    if startA is not None:
        hdr = find_header_cols(startA+1) or find_header_cols(startA+2) or find_header_cols(startA)
        if hdr:
            hr, preC, finC = hdr
            for r in range(hr+1, H):
                label = txt(r, 0)
                if not label or "계" in label:
                    break
                for key, aliases in QUAL_LABEL_MAP.items():
                    norm = flat(label)
                    if flat(key) in norm or any(a and flat(a) in norm for a in aliases):
                        out[key] = {"수정전": _to_int(txt(r, preC)), "최종": _to_int(txt(r, finC))}
                        break

    # 블록 B: 결함정도별 결함내역
    startB = None
    for r in range(H):
        line = "".join(txt(r, c) for c in range(W))
        if "결함정도" in line and "결함내역" in line:
            startB = r
            break
    if startB is not None:
        hdr = find_header_cols(startB+1) or find_header_cols(startB+2) or find_header_cols(startB)
        if hdr:
            hr, preC, finC = hdr
            for r in range(hr+1, H):
                label = txt(r, 0)
                if not label or "계" in label:
                    break
                for key in DEG_LABELS:
                    if key.lower() in label.lower():
                        out[key] = {"수정전": _to_int(txt(r, preC)), "최종": _to_int(txt(r, finC))}
                        break

    return out

# ─────────────────────────────────────────────────────
# fillMap 조립
# ─────────────────────────────────────────────────────

def build_fill_map(obj1: dict, obj2: dict, obj3: dict):
    """
    - 시트 "제품 정보 요청": 1번+2번 매핑
    - 시트 "결함정보": 3번 매핑
    (한 셀 내 2줄은 '\n')
    """
    # 1번 → “제품 정보 요청”
    b5 = "\n".join([obj1.get("국문명", ""), obj1.get("영문명", "")]).strip("\n")
    h7 = "\n".join([obj1.get("담당자-성 명", ""), obj1.get("담당자-FAX번호", "")]).strip("\n")
    c5 = "\n".join([obj1.get("국문명:", ""), obj1.get("영문명:", "")]).strip("\n")
    dept, title = "", ""
    if obj1.get("담당자-부서/직급"):
        parts = [x.strip() for x in obj1["담당자-부서/직급"].split("/", 1)]
        dept = parts[0] if len(parts) >= 1 else ""
        title = parts[1] if len(parts) >= 2 else ""

    prod_sheet = {
        # (1번 과정) 요구 순서에 맞는 좌표
        "D5": obj1.get("시험신청번호", ""),
        "N5": obj1.get("성적서 구분", ""),
        "B5": b5,                   # (국문명 / 영문명)
        "B7": obj1.get("사업자등록번호", ""),
        "C7": obj1.get("법인등록번호", ""),
        "D7": obj1.get("대표자", ""),
        "F7": obj1.get("대표자 E-Mail", ""),
        "E7": obj1.get("대표 전화번호", ""),
        "M7": obj1.get("홈페이지", ""),
        "G7": obj1.get("주 소", ""),
        "H7": h7,                   # (담당자-성 명 / 담당자-FAX번호)
        # 13. 건너뜀
        "I7": obj1.get("담당자-전화번호", ""),
        "K7": obj1.get("담당자-E- Mail", ""),
        "J7": obj1.get("담당자-Mobile", ""),
        "C5": c5,                   # (국문명: / 영문명:)
        "L7": "\n".join([dept, title]).strip("\n"),   # (부서 / 직급)

        # (2번 과정)
        "K5": "\n".join(obj2.get("시험기간", []) or []),
        "F5": obj2.get("개요 및 특성(설명)", "") or "",
        "G5": "\n".join(obj2.get("개요 및 특성(주요 기능)", []) or []),
        "H5": obj2.get("소요일수", 0),
    }

    # 3번 → “결함정보”
    defect_sheet = {
        "B4": obj3.get("결함차수", 0),
        "C4": obj3.get("적합성", {}).get("수정전", 0),
        "D4": obj3.get("효율성", {}).get("수정전", 0),
        "E4": obj3.get("호환성", {}).get("수정전", 0),
        "F4": obj3.get("사용성", {}).get("수정전", 0),
        "G4": obj3.get("신뢰성", {}).get("수정전", 0),
        "H4": obj3.get("보안성", {}).get("수정전", 0),
        "I4": obj3.get("유지보수성", {}).get("수정전", 0),
        "J4": obj3.get("이식성", {}).get("수정전", 0),
        "K4": obj3.get("요구사항", {}).get("수정전", 0),
        "L4": obj3.get("High", {}).get("수정전", 0),
        "M4": obj3.get("Medium", {}).get("수정전", 0),
        "N4": obj3.get("Low", {}).get("수정전", 0),
    }

    return {
        "제품 정보 요청": prod_sheet,
        "결함정보": defect_sheet,
    }
