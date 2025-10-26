import os, tempfile, json, logging
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from .report_docx_parser import build_pages

logger = logging.getLogger(__name__)   # django 로거 사용 (stdout로도 출력됨)

def _json_serialize(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)

@csrf_exempt
def parse_checkreport(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    files = request.FILES.getlist("file")
    if len(files) != 2:
        err = {"error":"docx 1개와 pdf 1개를 함께 업로드하세요."}
        logger.warning("[checkreport][resp] %s", _json_serialize(err))
        return JsonResponse(err, status=400)

    docx_file, pdf_file = None, None
    for f in files:
        name = (f.name or "").lower()
        if name.endswith(".docx"): docx_file = f
        elif name.endswith(".pdf"): pdf_file = f

    if not docx_file or not pdf_file:
        err = {"error":"docx 1개 + pdf 1개 조합이어야 합니다."}
        logger.warning("[checkreport][resp] %s", _json_serialize(err))
        return JsonResponse(err, status=400)

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

        data = build_pages(docx_path, pdf_path=pdf_path)

        # ★ 여기서 "원문 그대로" 직렬화한 텍스트를 로그로 남김
        serialized = _json_serialize(data)
        logger.info("[checkreport][resp] %s", serialized)

        # 클라이언트에는 기존대로 JsonResponse 반환
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        err = {"error": f"parse failed: {e}"}
        logger.exception("[checkreport][resp-error] %s", _json_serialize(err))
        return JsonResponse(err, status=500)
    finally:
        for p in (docx_path, pdf_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
