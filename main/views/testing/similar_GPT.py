import os
from django.conf import settings
from openai import OpenAI # ◀️ ollama 대신 openai 라이브러리 import

# ▼ OpenAI 클라이언트 초기화 (API 키 필요)
# 환경 변수에서 API 키를 가져오는 것이 가장 안전합니다.
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# run_ollama_with_reference_origin 함수를 아래와 같이 수정합니다.
def run_openai_with_reference(startDate, endDate, comment):
    # FILE_CONTEXT가 어디서 오는지 명확하지 않아 그대로 두었습니다.
    # 이 변수에 CSV 데이터가 문자열로 담겨 있어야 합니다.
    # 예: FILE_CONTEXT = "일련번호,인증번호,...\n1,GS-01-1234,..."
    
    # AI에게 전달할 프롬프트 (기존 내용과 거의 동일)
    prompt = f"""
    당신은 소프트웨어 제품 인증 데이터를 분석하는 AI입니다.
    다음은 참고할 전체 reference 데이터입니다:
    {FILE_CONTEXT}

    reference 데이터는 CSV 파일로 각 행이 1개의 데이터세트입니다.
    각 데이터세트는 다음 14개 항목명으로 구성됩니다:
    일련번호, 인증번호, 인증일자, 회사명, 제품, 등급, 시험번호, S/W분류, 제품 설명, 총WD, 재계약, 특이사항, "시작날짜/종료날짜", 시험원

    각 항목은 CSV에서 헤더로 존재하며, 한 행이 하나의 데이터세트를 나타냅니다.

    다음 조건에 맞는 인증 데이터를 reference 데이터 내에서 필터링해 유사 제품을 찾아주세요:

    1. 인증일자 조건: 인증일자 값이 {startDate} ~ {endDate} 범위에 포함될 것
    - {startDate}, `{endDate}`가 공백이거나 비어 있을 경우 이 조건은 무시함
    - 날짜는 `YYYY-MM-DD` 형식으로 입력된다고 가정

    2. 제품 설명 유사도 조건: 아래의 설명과 기능, 용도, 기술적 특성 측면에서 의미적으로 유사할 것
    - 설명: "{comment}"
    - 비교 시 단어 수준 키워드 매칭뿐만 아니라 문장 의미 임베딩 기반 유사도 비교 수행
    - 제품 설명 필드가 비어 있거나 null인 데이터는 제외함

    3. 출력 형식은 요청한 JSON 리스트 형태로만 출력하세요.
    - JSON 이외의 설명, 문장 출력 절대 금지
    - `similarity`는 1~5 범위의 정수로, 유사도 판단 점수를 의미 (5: 매우 유사, 4: 유사, 3: 약간 유사, 2 이하: 유사하지 않음 → 출력 제외)

    ⛔️⛔️ 주의: JSON 이외의 문장 출력 금지. 설명·요약·해석 절대 포함 금지.
    """
    
    try:
        # ▼ OpenAI API 호출 부분
        response = client.chat.completions.create(
            model="gpt-4o",  # 또는 "gpt-4-turbo" 등 원하는 모델 사용
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"} # ◀️ JSON 모드 활성화
        )
        # ▼ 응답에서 실제 텍스트 추출
        return response.choices[0].message.content
    
    except Exception as e:
        print("[ERROR]", e)
        return f"OpenAI 처리 중 오류 발생: {str(e)}"
