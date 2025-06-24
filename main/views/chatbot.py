# main/views/chatbot.py

import os
from django.conf import settings
from ollama import generate

def run_ollama_with_reference_origin(startDate, endDate, comment):
    user_input = "\n".join([startDate, endDate, comment])

    prompt = f"""
    당신은 소프트웨어 제품 인증 데이터를 분석하는 AI입니다.  
    다음은 참고할 전체 reference 데이터입니다:  
    {FILE_CONTEXT}  
    
    reference 데이터는 CSV 파일로 각 행이 1개의 데이터세트입니다.  
    각 데이터세트는 다음 14개 항목명으로 구성됩니다:  
    일련번호, 인증번호, 인증일자, 회사명, 제품, 등급, 시험번호, S/W분류, 제품 설명, 총WD, 재계약, 특이사항, "시작날짜/종료날짜", 시험원  
    
    각 항목은 CSV에서 헤더로 존재하며, 한 행이 하나의 데이터세트를 나타냅니다.  
    
    다음 조건에 맞는 인증 데이터를 reference 데이터 내에서 필터링해 유사 제품을 찾아주세요:  
    
    1. **인증일자 조건**: 인증일자 값이 `{startDate}` ~ `{endDate}` 범위에 포함될 것  
    - `{startDate}`, `{endDate}`가 공백이거나 비어 있을 경우 이 조건은 무시함  
    - 날짜는 `YYYY-MM-DD` 형식으로 입력된다고 가정  
    
    2. **제품 설명 유사도 조건**: 아래의 설명과 기능, 용도, 기술적 특성 측면에서 의미적으로 유사할 것  
    - 설명: "{comment}"  
    - 비교 시 단어 수준 키워드 매칭뿐만 아니라 문장 의미 임베딩 기반 유사도 비교 수행  
    - `제품 설명` 필드가 비어 있거나 null인 데이터는 제외함  
    
    3. 출력 형식은 다음과 같은 JSON 리스트 형태로만 출력하세요.  
    - **JSON 이외의 설명, 문장 출력 절대 금지**  
    - `similarity`는 1~5 범위의 정수로, 유사도 판단 점수를 의미 (5: 매우 유사, 4: 유사, 3: 약간 유사, 2 이하: 유사하지 않음 → 출력 제외)  
    
    ```json
    [
        {
            "a1": "일련번호",
            "a2": "인증번호",
            "a3": "인증일자",
            "a4": "회사명",
            "a5": "제품",
            "a6": "등급",
            "a7": "시험번호",
            "a8": "S/W분류",
            "a9": "제품 설명",
            "a10": "총WD",
            "a11": "재계약",
            "a12": "특이사항",
            "a13": "시작날짜/종료날짜",
            "a14": "시험원",
            "similarity": "1~5 중 유사도 점수 (정수)"
        },
        ...
    ]        
    
    ⛔⛔ 주의: JSON 이외의 문장 출력 금지. 설명·요약·해석 절대 포함 금지.
    """
        
    try:
        response = generate(model='gemma3', prompt=prompt)
        return response.get("response", "[응답 없음]")
    except Exception as e:
        print("[ERROR]", e)
        return f"Ollama 처리 중 오류 발생: {str(e)}"
