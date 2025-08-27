from django.http import FileResponse, Http404
from django.conf import settings
import os

# 원본 엑셀의 서버 내부 경로(공개하지 않음)
ORIGIN_XLSX_PATH = os.path.join(settings.BASE_DIR, "main/data/prdinfo.xlsx")

def source_excel_view(request):
    # (선택) 인증/권한 체크
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    if not os.path.exists(ORIGIN_XLSX_PATH):
        raise Http404()
    resp = FileResponse(open(ORIGIN_XLSX_PATH, "rb"),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    # 캐시 제어/보안 헤더
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=60"  # 필요에 맞게
    # 다운로드용 파일명 힌트
    resp["Content-Disposition"] = 'inline; filename="prdinfo.xlsx"'
    return resp
