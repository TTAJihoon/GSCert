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

def run_ollama_with_reference(q1, q2, q3, q4, q5):
    user_input = "\n".join([q1, q2, q3, q4, q5])

    prompt = f"""다음은 참고 파일 내용입니다:

{FILE_CONTEXT}

사용자 질문:
{user_input}

※ 반드시 위 파일 내용만 기반으로 답변해 주세요. 외부 지식은 사용하지 마세요."""

    try:
        response = generate(model='gemma3', prompt=prompt)
        return response.get("response", "[응답 없음]")
    except Exception as e:
        print("[ERROR]", e)
        return f"Ollama 처리 중 오류 발생: {str(e)}"
