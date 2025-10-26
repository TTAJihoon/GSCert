# main/views/review/checkreport_api.py
import os, tempfile
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from .report_docx_parser import build_pages

@csrf_exempt  # 템플릿에서 CSRF 이미 넣으셨다면 제거해도 됩니다.
def parse_checkreport(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    files = request.FILES.getlist("file")
    if len(files) != 2:
        return JsonResponse({"error": "docx 1개와 pdf 1개를 함께 업로드하세요."}, status=400)

    docx_file, pdf_file = None, None
    for f in files:
        name = (f.name or "").lower()
        if name.endswith(".docx"):
            docx_file = f
        elif name.endswith(".pdf"):
            pdf_file = f

    if not docx_file or not pdf_file:
        return JsonResponse({"error": "docx 1개 + pdf 1개 조합이어야 합니다."}, status=400)

    # 임시 저장
    tmp_dir = tempfile.gettempdir()
    docx_path = os.path.join(tmp_dir, next(tempfile._get_candidate_names()) + ".docx")
    pdf_path  = os.path.join(tmp_dir, next(tempfile._get_candidate_names()) + ".pdf")

    try:
        with open(docx_path, "wb") as out:
            for chunk in docx_file.chunks():
                out.write(chunk)
        with open(pdf_path, "wb") as out:
            for chunk in pdf_file.chunks():
                out.write(chunk)

        # 핵심: 기존 파서 호출 (원본 그대로 반환)
        data = build_pages(docx_path, pdf_path=pdf_path)
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({"error": f"parse failed: {e}"}, status=500)
    finally:
        # 임시파일 정리(실패시에도 삭제 시도)
        for p in (docx_path, pdf_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
