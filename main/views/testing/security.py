import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from .security_extractHTML import extract_vulnerability_sections

# @csrf_exempt # [제거] Django의 기본 CSRF 보호 기능 사용
@require_http_methods(["POST"])
def invicti_parse_view(request):
    if not request.FILES.getlist('file'):
        return JsonResponse({"error": "업로드된 파일이 없습니다."}, status=400)

    all_rows = []
    css_data = ""

    try:
        for i, uploaded_file in enumerate(request.FILES.getlist('file')):
            if not uploaded_file.name.lower().endswith(('.html', '.htm')):
                return JsonResponse({"error": f"잘못된 파일 형식입니다: {uploaded_file.name}"}, status=400)

            # [개선] 대용량 파일 처리 시 메모리 문제를 방지하기 위해 파일 크기 제한
            if uploaded_file.size > 10 * 1024 * 1024: # 예: 10MB 제한
                return JsonResponse({"error": f"파일 크기가 너무 큽니다 (10MB 제한): {uploaded_file.name}"}, status=400)

            html_content = uploaded_file.read().decode('utf-8')
            parsed_data = extract_vulnerability_sections(html_content)

            if i == 0: # 첫 번째 파일의 CSS만 사용
                css_data = parsed_data.get("css", "")

            all_rows.extend(parsed_data.get("rows", []))

    except Exception as e:
        return JsonResponse({"error": f"파일 처리 중 오류가 발생했습니다: {str(e)}"}, status=500)

    final_data = {
        "css": css_data,
        "rows": all_rows
    }

    return JsonResponse(final_data)
