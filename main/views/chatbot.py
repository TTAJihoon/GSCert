import os
from django.conf import settings
from ollama import generate

# ✅ 서버 시작 시 1회만 파일 읽기
try:
    REFERENCE_FILE_PATH = os.path.join(settings.BASE_DIR, 'main', 'data', 'reference.csv')
    with open(REFERENCE_FILE_PATH, 'r', encoding='utf-8') as f:
        FILE_CONTEXT = f.read()
    print("[INFO] reference.csv loaded once into memory.")
except FileNotFoundError:
    FILE_CONTEXT = "[오류] reference.csv 파일을 찾을 수 없습니다."
    print("[ERROR] reference.csv 파일 없음")

def run_ollama_with_reference(q1, q2, q3, q4, q5):
    user_input = "\n".join([q1, q2, q3, q4, q5])

    prompt = f"""다음은 참고 파일 내용입니다:

{FILE_CONTEXT}

사용자 질문:
{user_input}

※ 반드시 위 파일 내용만 기반으로 답변해 주세요. 외부 지식은 사용하지 마세요."""

    try:
        print("[DEBUG] prompt:", prompt)
        response = generate(model='gemma3', prompt=prompt)
        print("[DEBUG] response:", response)
        return response.get("response", "[응답 없음]")
    except Exception as e:
        print("[ERROR]", e)
        return f"Ollama 처리 중 오류 발생: {str(e)}"
