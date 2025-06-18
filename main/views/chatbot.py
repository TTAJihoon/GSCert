# main/views/chatbot.py

import os
from django.conf import settings
from ollama import generate
from main.utils.constants import REFERENCE_PATH

# 전역 캐시 변수
FILE_CONTEXT = None

def reload_reference_context():
    global FILE_CONTEXT
    try:
        with open(REFERENCE_PATH, 'r', encoding='utf-8') as f:
            FILE_CONTEXT = f.read()
        print("[INFO] FILE_CONTEXT reloaded.")
    except FileNotFoundError:
        FILE_CONTEXT = "[오류] reference.csv 파일을 찾을 수 없습니다."
        print("[ERROR] reference.csv 파일 없음.")

# 초기 1회 로딩
reload_reference_context()

def run_ollama_with_reference(startDate, endDate, comment):
    user_input = "\n".join([startDate, endDate, comment])

    prompt = f"""
    당신은 소프트웨어 제품 인증 데이터를 분석하는 AI입니다.
    다음은 참고할 전체 reference 데이터입니다:
    {FILE_CONTEXT}
    reference 데이터는 csv 파일로 각 행이 1개의 데이터세트입니다.
    각 데이터세트는 일련번호,인증번호,인증일자,회사명,제품,등급,시험번호,S/W분류,제품 설명,총WD,재계약,특이사항,"시작날짜/
종료날짜",시험원 순서의 14개의 항목명으로 이루어져 있습니다.
    다른 정보를 전혀 사용하지 않고 reference 데이터에서만 다음 조건에 맞는 인증 데이터를 필터링해 유사 제품을 찾아주세요:
    
    1. 인증일자가 {startDate} ~ {endDate} 범위에 포함될 것
    2. 제품 설명이 다음 설명과 SW적 기능, 용도, 기술적 특성에서 유사할 것:
    - 설명: "{comment}"
    위 조건과 맞는 각 데이터세트를 찾아서 아래 형식의 JSON 리스트를 만들어주세요.
    
    🛑🛑🛑 반드시 아래와 같은 형식의 JSON 리스트만 출력하세요. 필드명도 정확히 아래와 같이 사용할 것.
    형식이 다르거나 설명이 섞이면 파싱이 실패합니다. 설명도 출력하지 마세요.
    각 필드명은 데이터세트의 항목명과 같습니다.
    
    [
        {{
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
        }},
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
