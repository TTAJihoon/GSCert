import os
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
import openai

@require_http_methods(["POST"])
def get_gpt_recommendation_view(request):
    try:
        # OpenAI API 키 환경 변수에서 로드
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return JsonResponse({"error": "OpenAI API 키가 서버에 설정되지 않았습니다."}, status=500)
        
        client = openai.OpenAI(api_key=api_key)

        # 프론트엔드에서 보낸 프롬프트 데이터 로드
        data = json.loads(request.body)
        prompt = data.get('prompt')

        if not prompt:
            return HttpResponseBadRequest("프롬프트 내용이 없습니다.")

        # OpenAI API 호출
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "당신은 보안 전문가입니다. 주어진 취약점 보고서 내용을 바탕으로, 개발자가 이해하기 쉽도록 구체적인 조치 방법을 단계별로 설명하는 수정 가이드를 한국어로 작성해주세요."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-5-nano",
        )
        
        recommendation = chat_completion.choices[0].message.content
        
        return JsonResponse({"recommendation": recommendation})

    except json.JSONDecodeError:
        return HttpResponseBadRequest("잘못된 JSON 형식입니다.")
    except Exception as e:
        return JsonResponse({"error": f"API 호출 중 오류 발생: {str(e)}"}, status=500)
