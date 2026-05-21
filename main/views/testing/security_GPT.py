import json
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from main.utils.gemini_gemma import (
    GemmaConfigError,
    GemmaGenerationError,
    generate_gemma_text,
    generate_gemma_text_stream,
)


def _build_security_recommendation_prompt(prompt):
    return f"""
You are a professional security expert.
Your answers should be clear, concise, and directly address the security report content provided by the user.
Use GitHub-Flavored Markdown when it improves readability.
Use tables only when comparing items or presenting step-by-step checks.
Do not wrap the whole answer in a code block.
Do not assume the report is always a real vulnerability.

Task:
1. First decide whether the provided content describes a real security defect or vulnerability.
2. If it is a real defect, explain why it is a defect and provide concrete remediation steps.
3. If it is not a defect, explain why it should not be treated as a defect and do not provide unnecessary remediation steps.
4. If the information is insufficient, say that it is not possible to determine and list the missing evidence.

Recommended Markdown structure:
- `## 판단`
- `## 근거`
- `## 수정 방안` only when it is a real defect
- `## 결함으로 보기 어려운 이유` when it is not a defect

사용자 프롬프트:
{prompt}
"""

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

    ai_prompt = _build_security_recommendation_prompt(prompt)
    try:
        response_content = generate_gemma_text(ai_prompt)
        return JsonResponse({"response": response_content})
    except GemmaConfigError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except GemmaGenerationError as e:
        return JsonResponse({"error": f"Gemma API 호출 중 오류 발생: {e}"}, status=500)
    except Exception as e:
        return JsonResponse({"error": f"AI 추천 생성 중 오류 발생: {e}"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def stream_gpt_recommendation_view(request):
    try:
        data = json.loads(request.body)
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({"error": "프롬프트 내용이 없습니다."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "잘못된 요청 형식입니다."}, status=400)

    ai_prompt = _build_security_recommendation_prompt(prompt)

    def stream():
        try:
            for chunk in generate_gemma_text_stream(ai_prompt):
                yield chunk
        except GemmaConfigError as exc:
            yield f"\n\n[오류] {exc}"
        except GemmaGenerationError as exc:
            yield f"\n\n[오류] Gemma API 호출 중 오류 발생: {exc}"
        except Exception as exc:
            yield f"\n\n[오류] AI 추천 생성 중 오류 발생: {exc}"

    response = StreamingHttpResponse(stream(), content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
