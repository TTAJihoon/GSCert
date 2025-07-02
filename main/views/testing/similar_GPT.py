import os
from openai import OpenAI
from main.utils import reload_reference.py

# OpenAI API 키로 클라이언트 초기화
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 인사하는 챗봇 함수로 수정
def run_openai_GPT(comment):
    reference = getREF()  # 서버 시작 시 캐싱된 데이터 사용
    prompt = f"""
    
    참고용 데이터의 '일련번호'가 5555인 데이터 행의 값을 컬럼명과 함께 표시해줘.
    컬럼은 '일련번호'가 포함된 행이야.
    아래는 참고할 데이터야. 해당 데이터에 있는 값만 대답에 사용해줘.
    {reference}

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
