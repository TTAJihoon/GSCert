import re
from openpyxl import load_workbook

# ── 유틸 ─────────────────────────────────
def normalize_spaces(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\u200b", " ").replace("\xa0", " ")).strip()

def flat(s: str) -> str:
    return re.sub(r"\s+", "", normalize_spaces(s))

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

# ── 라벨/등급 ────────────────────────────
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

# ── 메인: 결함리포트 파서 ────────────────
def extract_process3_xlsx_defects(byts, filename):
    wb = load_workbook(byts, data_only=True)
    sh = wb["시험분석자료"] if "시험분석자료" in wb.sheetnames else None

    out = {"결함차수": _defect_round_from_filename(filename)}
    for k in QUAL_LABEL_MAP.keys():
        out[k] = {"수정전": 0, "최종": 0}
    for k in DEG_LABELS:
        out[k] = {"수정전": 0, "최종": 0}
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
            pre_idx, fin_idx = None, None
            for i, v in enumerate(row):
                if re.search("수정", v): pre_idx = i
                if "최종" in v: fin_idx = i
            if pre_idx is not None and fin_idx is not None:
                return r, pre_idx, fin_idx
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
                norm = flat(label)
                for key, aliases in QUAL_LABEL_MAP.items():
                    if flat(key) in norm or any(flat(a) in norm for a in aliases if a):
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
