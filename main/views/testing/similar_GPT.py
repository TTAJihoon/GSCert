import os
from openai import OpenAI

# OpenAI API 키로 클라이언트 초기화
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 인사하는 챗봇 함수로 수정
def run_openai_GPT(comment):
    prompt = f"""
    너는 사용자의 인사에 친절하게 응답하는 인공지능 챗봇이야.
    사용자가 아래와 같은 말을 하면 적절한 인사로 응답해줘.

    사용자 입력: "{comment}"
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # 또는 원하는 모델명
            messages=[
                {"role": "system", "content": "너는 친절하고 밝은 인사 챗봇이야."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[ERROR]", e)
        return f"OpenAI 처리 중 오류 발생: {str(e)}"
