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

# 품질특성 9개, 결함정도 3개 — "E열"에서 읽어온 순서대로 매핑
QUAL_ORDER = [
    "적합성", "효율성", "호환성", "사용성", "신뢰성",
    "보안성", "유지보수성", "이식성", "요구사항",
]
DEG_ORDER = ["High", "Medium", "Low"]

def extract_process3_xlsx_defects(byts, filename):
    wb = load_workbook(byts, data_only=True)
    sh = wb["시험분석자료"] if "시험분석자료" in wb.sheetnames else None

    out = {"결함차수": _defect_round_from_filename(filename)}
    # 초기화
    for k in QUAL_ORDER:
        out[k] = {"수정전": 0, "최종": 0}
    for k in DEG_ORDER:
        out[k] = {"수정전": 0, "최종": 0}
    if sh is None:
        return out

    # values[r][c] (0-based) 매트릭스
    values = [[(cell.value if cell.value is not None else "") for cell in row] for row in sh.iter_rows()]
    H = len(values)
    W = max((len(r) for r in values), default=0)

    def txt(r, c):
        try:
            return normalize_spaces(values[r][c])
        except Exception:
            return ""

    def find_row_in_col_d(keyword: str):
        target = flat(keyword)
        for r in range(H):
            v = txt(r, 3)  # D열 = index 3
            if v and target in flat(v):
                return r
        return None

    def pick_e_column_series(start_r: int, end_r: int):
        """E열(index 4)에서 start_r..end_r (inclusive) 값을 _to_int로 변환하여 리스트 반환"""
        res = []
        for r in range(max(0, start_r), min(H, end_r + 1)):
            res.append(_to_int(txt(r, 4)))
        return res

    # 1) 품질특성별 결함내역: D에서 찾고 E열 r+2..r+10 → 9개
    rA = find_row_in_col_d("품질특성별 결함내역")
    if rA is not None:
        vals = pick_e_column_series(rA + 2, rA + 10)
        # 길이 보정(부족하면 0 패딩, 많으면 9개만)
        if len(vals) < 9:
            vals = vals + [0] * (9 - len(vals))
        vals = vals[:9]
        for i, key in enumerate(QUAL_ORDER):
            out[key]["수정전"] = vals[i]

    # 2) 결함정도별 결함내역: D에서 찾고 E열 r+2..r+4 → 3개 (High, Medium, Low)
    rB = find_row_in_col_d("결함정도별 결함내역")
    if rB is not None:
        vals = pick_e_column_series(rB + 2, rB + 4)
        if len(vals) < 3:
            vals = vals + [0] * (3 - len(vals))
        vals = vals[:3]
        for i, key in enumerate(DEG_ORDER):
            out[key]["수정전"] = vals[i]

    return out
