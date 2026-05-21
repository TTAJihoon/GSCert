import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from main.utils.gemini_gemma import GemmaConfigError, GemmaGenerationError, generate_gemma_text

@csrf_exempt
@require_http_methods(["POST"])
def get_gpt_recommendation_view(request):
    """
    프론트엔드로부터 받은 프롬프트를 Gemini API의 Gemma 모델에게 보내고, 답변을 반환합니다.
    """
    try:
        data = json.loads(request.body)
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({"error": "프롬프트 내용이 없습니다."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "잘못된 요청 형식입니다."}, status=400)

    ai_prompt = f"""
You are a professional security expert.
Your answers should be clear, concise, and directly address the vulnerability described.
Return only the recommendation text.

사용자 프롬프트:
{prompt}
"""
    try:
        response_content = generate_gemma_text(ai_prompt)
        return JsonResponse({"response": response_content})
    except GemmaConfigError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except GemmaGenerationError as e:
        return JsonResponse({"error": f"Gemma API 호출 중 오류 발생: {e}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"AI 추천 생성 중 오류 발생: {e}"}, status=500)
