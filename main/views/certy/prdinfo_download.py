import os
from io import BytesIO
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from openpyxl import load_workbook
import json
import threading

# 원본 템플릿 경로 (기존 소스와 동일한 위치 가정)
ORIGIN_XLSX_PATH = os.path.join(settings.BASE_DIR, "main/data/prdinfo.xlsx")

# ── 1회 로드용 캐시 (디스크 읽기 병목 제거)
_TEMPLATE_BYTES = None
_TEMPLATE_LOCK = threading.Lock()

def _get_template_bytes() -> bytes:
    global _TEMPLATE_BYTES
    if _TEMPLATE_BYTES is not None:
        return _TEMPLATE_BYTES
    with _TEMPLATE_LOCK:
        if _TEMPLATE_BYTES is None:
            with open(ORIGIN_XLSX_PATH, "rb") as f:
                _TEMPLATE_BYTES = f.read()
    return _TEMPLATE_BYTES

def _write_row(ws, start_cell: str, values):
    """
    start_cell부터 오른쪽으로 values를 쭉 기록(B5 -> C5 -> ...).
    """
    from openpyxl.utils import coordinate_to_tuple, get_column_letter
    row, col = coordinate_to_tuple(start_cell)
    for i, v in enumerate(values):
        ws[f"{get_column_letter(col + i)}{row}"] = v if v is not None else ""

@require_POST
@csrf_protect
def download_filled_prdinfo(request):
    """
    Luckysheet에서 지정된 범위의 값을 받아, 템플릿 사본에 값을 채워서 곧바로 다운로드 응답.
    서버에 저장(덮어쓰기)하지 않음.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    # 기대 페이로드 스키마(프런트 코드와 1:1)
    # {
    #   "prdinfo": {
    #       "row_B5_N5": [...13개...],
    #       "row_B7_N7": [...13개...],
    #       "B9": str, "D9": str, "F9": str, "G9": str, "H9": str, "J9": str, "L9": str
    #   },
    #   "defect": {
    #       "row_B4_N4": [...13개...]
    #   }
    # }
    try:
        prdinfo = payload.get("prdinfo", {})
        defect  = payload.get("defect", {})

        vals_B5_N5 = prdinfo.get("row_B5_N5", [])
        vals_B7_N7 = prdinfo.get("row_B7_N7", [])
        B9 = prdinfo.get("B9", ""); D9 = prdinfo.get("D9", "")
        F9 = prdinfo.get("F9", ""); G9 = prdinfo.get("G9", "")
        H9 = prdinfo.get("H9", ""); J9 = prdinfo.get("J9", "")
        L9 = prdinfo.get("L9", "")

        vals_B4_N4 = defect.get("row_B4_N4", [])
    except Exception:
        return HttpResponseBadRequest("Missing fields")

    # 템플릿 메모리 사본 로드
    tpl_bytes = _get_template_bytes()
    wb = load_workbook(BytesIO(tpl_bytes))
    ws_prd = wb["제품 정보 요청"]
    ws_def = wb["결함정보"]

    # 값 채우기 (템플릿의 서식/병합은 그대로 유지)
    # - 제품 정보 요청
    _write_row(ws_prd, "B5", vals_B5_N5)
    _write_row(ws_prd, "B7", vals_B7_N7)
    ws_prd["B9"] = B9; ws_prd["D9"] = D9; ws_prd["F9"] = F9
    ws_prd["G9"] = G9; ws_prd["H9"] = H9; ws_prd["J9"] = J9; ws_prd["L9"] = L9

    # - 결함정보
    _write_row(ws_def, "B4", vals_B4_N4)

    # 메모리에 저장 후 즉시 다운로드 응답
    out = BytesIO()
    wb.save(out)
    out.seek(0)

    resp = HttpResponse(
        out.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="prdinfo_filled.xlsx"'
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
