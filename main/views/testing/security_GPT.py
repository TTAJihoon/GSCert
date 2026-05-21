import json
import os
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from main.utils.gemini_gemma import (
    GemmaConfigError,
    GemmaGenerationError,
    GemmaRateLimitError,
    generate_gemma_text,
    generate_gemma_text_stream,
)


DEFAULT_SECURITY_FALLBACK_MODELS = "gemini-3.1-flash-lite"
DEFAULT_SECURITY_RETRIES = 2


def _env_int(name, default):
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _security_model_settings():
    return {
        "model": os.environ.get("GEMINI_SECURITY_MODEL") or os.environ.get("GEMINI_MODEL"),
        "fallback_models": os.environ.get("GEMINI_SECURITY_FALLBACK_MODELS")
        or os.environ.get("GEMINI_FALLBACK_MODELS")
        or DEFAULT_SECURITY_FALLBACK_MODELS,
        "retries": _env_int("GEMINI_SECURITY_RETRIES", DEFAULT_SECURITY_RETRIES),
    }


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
    model_settings = _security_model_settings()
    try:
        response_content = generate_gemma_text(ai_prompt, **model_settings)
        return JsonResponse({"response": response_content})
    except GemmaConfigError as e:
        return JsonResponse({"error": str(e)}, status=500)
    except GemmaRateLimitError:
        return JsonResponse(
            {"error": "AI 모델 호출 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."},
            status=429,
        )
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
    model_settings = _security_model_settings()

    def stream():
        try:
            for chunk in generate_gemma_text_stream(ai_prompt, **model_settings):
                yield chunk
        except GemmaConfigError as exc:
            yield f"\n\n__GSCERT_AI_ERROR__:{exc}"
        except GemmaRateLimitError:
            yield "\n\n__GSCERT_AI_RATE_LIMIT__:AI 모델 호출 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."
        except GemmaGenerationError as exc:
            yield "\n\n__GSCERT_AI_ERROR__:AI 서버가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요."
        except Exception as exc:
            yield f"\n\n__GSCERT_AI_ERROR__:AI 추천 생성 중 오류 발생: {exc}"

    response = StreamingHttpResponse(stream(), content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
