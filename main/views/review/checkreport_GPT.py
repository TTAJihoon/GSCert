import os
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from openai import OpenAI

@csrf_exempt
@require_http_methods(["POST"])
def get_gpt_recommendation_view(request):
    """
    프론트엔드로부터 받은 프롬프트를 OpenAI GPT 모델에게 보내고, 답변을 반환합니다.
    """
    # 1. API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JsonResponse({"error": "OpenAI API 키가 설정되지 않았습니다. 환경 변수를 확인하세요."}, status=500)

    # 2. 요청 데이터 파싱
    try:
        data = json.loads(request.body)
        prompt = data.get('prompt')
        if not prompt:
            return JsonResponse({"error": "프롬프트 내용이 없습니다."}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({"error": "잘못된 요청 형식입니다."}, status=400)

    # 3. OpenAI API 호출
    try:
        client = OpenAI(api_key=api_key)
        
        # 요청하신 GPT 모델명 사용
        model_name = "gpt-5-nano"

        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional security expert. Your answers should be clear, concise, and directly address the vulnerability described."},
                {"role": "user", "content": prompt}
            ]
        )
        
        response_content = completion.choices[0].message.content
        
        return JsonResponse({"response": response_content})

    except Exception as e:
        error_message = str(e)
        # 사용자가 존재하지 않는 모델명을 사용했을 경우 더 친절한 안내를 제공
        if "The model `gpt-5-nano` does not exist" in error_message:
            error_message = "GPT 모델('gpt-5-nano')을 찾을 수 없습니다. 모델명을 확인하거나 OpenAI API Plan을 확인하세요."
        
        return JsonResponse({"error": f"GPT API 호출 중 오류 발생: {error_message}"}, status=500)
