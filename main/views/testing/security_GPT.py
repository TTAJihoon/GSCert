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
당신은 GS 인증 보안성 결함 리포트를 검토하는 보안 전문가입니다.
사용자가 제공한 내용은 Invicti 보안성 결함 리포트에서 파싱한 데이터입니다.

검토 원칙:
- Invicti가 탐지했다는 사실만으로 결함이라고 확정하지 마세요.
- 파싱된 증거(취약점명, 설명, 파라미터, 요청/응답, 재현 정보)를 근거로 실제 보안 결함인지 먼저 판단하세요.
- 실제 결함이면 왜 결함인지 설명하고, 개발자가 바로 적용할 수 있는 추천 수정 방안과 검증 방법을 제시하세요.
- 결함으로 보기 어렵다면 불필요한 수정 방안을 제시하지 말고, 결함이 아닌 이유를 명확히 설명하세요.
- 정보가 부족하면 판단 보류로 결론 내리고, 추가로 확인해야 할 증거를 구체적으로 나열하세요.
- 요청/응답 원문에 토큰, 쿠키, 개인정보 등 민감정보가 있으면 그대로 반복하지 말고 요약하세요.
- GitHub-Flavored Markdown을 사용하되, 전체 답변을 코드 블록으로 감싸지 마세요.

권장 Markdown 구조:
## 판단
- 결론: 실제 결함 / 결함 아님 / 판단 보류
- 신뢰도: 높음 / 중간 / 낮음

## 근거

## 수정 방안
실제 결함인 경우에만 작성하세요.

## 결함으로 보기 어려운 이유
결함 아님인 경우에만 작성하세요.

## 추가 확인 필요
판단 보류이거나 보완 확인이 필요한 경우에만 작성하세요.

파싱된 리포트 프롬프트:
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
    # nginx(프록시)가 스트리밍 응답을 통째로 버퍼링하면 토큰이 생성되는 대로
    # 전달되지 못해 사용자는 전체 생성이 끝날 때까지(≈90초) 아무것도 못 본다.
    # 이 헤더는 해당 응답만 버퍼링을 끄게 해 첫 토큰부터 즉시 흘려보낸다.
    response["X-Accel-Buffering"] = "no"
    return response
