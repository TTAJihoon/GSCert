import os
import re
import json
from datetime import datetime
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from openai import OpenAI
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# GPT API 초기화
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def run_openai_GPT(query): # 문장당 유사제품 검색 개수
    print("[STEP 1] 사용자 질문 수신:", query)
    prompt = f"""
    너는 SW 프로그램의 매뉴얼의 내용을 참고해서 제 3자에게 제품을 설명하기 위한 한 문장의 제품 개요를 작성하는 SW 제품 설명 전문가야.
    아래 내용을 참고해서 한 문장의 요약문 외의 말은 하지말아줘.
    1. 실무적이고 소프트웨어 중심의 톤으로 “~을 지원/제공하는 ~솔루션/시스템/플랫폼/프로그램” 형식의 100자 미만 문장으로 작성해줘.
    2. 문장의 마지막은 가장 범용적인 단어를 사용해서 작성해줘. 예를들면 RAG, LLM, EAI, LMS, DBMS 등의 대표적인 단어를 사용해줘.
    3. LLM, AI, 클라우드, IoT 등 제품에서 사용하는 특정 기술명이 포함된 내용이 있다면 작성해줘.
    4. 문장 끝은 ‘솔루션’, ‘시스템’, ‘플랫폼’, ‘프로그램’ 중 하나로만 작성해줘.
    5. ‘소프트웨어 솔루션’ 또는 ‘플랫폼 솔루션’ 등 중복/유사 표현은 절대 사용하지 마.
    6. 본 제품명이나 제조사는 반드시 제외해줘.
    7. 하지만 쿠버네티스와 연동하는~, AWS 연동 서비스와~ 처럼 해당 제품이 아닌 연동제품의 경우에는 제품명이나 제조사를 작성해도 돼.
    아래는 요약 대상 매뉴얼 텍스트야:
    \"\"\"{query}\"\"\"
    """
    
    print("[STEP 2] GPT 요청 시작")
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}]
        )
        # GPT 결과 문장만 추출
        result_text = response.choices[0].message.content.strip()
        print("[STEP 3] GPT 응답 완료:", result_text)
        return result_text

    except Exception as e:
        print("[ERROR] GPT 응답 실패:", e)
        return "❌ GPT 응답 생성 중 오류가 발생했습니다."
