from main.utils.gemini_gemma import GemmaConfigError, GemmaGenerationError, generate_gemma_text


def run_gemini_gemma(query):
    """Gemini API hosted Gemma 모델로 제품 개요를 한 문장으로 요약한다."""
    source_text = "\n".join(query) if isinstance(query, (list, tuple)) else str(query)
    print("[STEP 1] 사용자 질문 수신:", source_text[:500])
    prompt = f"""
    너는 SW 프로그램 매뉴얼 내용을 참고하여 제3자에게 제품을 설명하는 SW 제품 설명 전문가이다.  
    아래 조건에 따라 한 문장의 제품 개요를 100자 미만으로 작성하라.  

    1. 실무적이고 소프트웨어 중심의 톤으로 “~을 지원/제공하는 ~솔루션/시스템/플랫폼/프로그램” 형식으로 작성한다.
    2. 마지막을 끝맺을때는 해당 제품을 가장 잘 설명할 수 있는 단어 1개를 선택하여 추가한다. 예를 들면 쇼핑몰 시스템, DBMS 솔루션 등.
    3. 문장 끝에 추가하는 단어(RAG, LLM, EAI, LMS, DBMS 등)는 입력 문장에 해당 기술명이나 연관 내용이 명확히 포함되어 있을 단어만 문장 끝에 넣는다.
       그렇지 않으면 넣지 않는다.
    4. ‘소프트웨어 솔루션’ 또는 ‘플랫폼 솔루션’ 등 중복/유사 표현은 절대 사용하지 않는다.  
    5. 본 제품명이나 제조사는 반드시 제외한다. 단, 해당 제품과 연동하는 쿠버네티스, AWS 등 연동 제품명은 작성 가능하다.  
    6. 요약 대상 메뉴얼 텍스트에 포함되지 않은 임의의 기술명, 기능, 연관 단어를 추가하지 않는다.  
    7. 오직 매뉴얼에 작성된 내용에만 기반하여 한 문장으로 요약문만 작성하고, 요약문 외에는 어떠한 문구도 제공 금지.
    아래는 요약 대상 매뉴얼 텍스트야:
    \"\"\"{source_text}\"\"\"
    """
    
    print("[STEP 2] Gemini/Gemma 요청 시작")
    try:
        result_text = generate_gemma_text(prompt)
        print("[STEP 3] Gemini/Gemma 응답 완료:", result_text)
        return result_text

    except GemmaConfigError as e:
        print("[ERROR] Gemini/Gemma 설정 오류:", e)
        return f"❌ {e}"
    except GemmaGenerationError as e:
        print("[ERROR] Gemini/Gemma 응답 실패:", e)
        return "❌ Gemma 응답 생성 중 오류가 발생했습니다."


# 기존 import 경로 호환용. 새 코드에서는 run_gemini_gemma를 직접 사용하는 것을 권장한다.
def run_openai_GPT(query):
    return run_gemini_gemma(query)
