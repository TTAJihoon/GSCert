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
    당신은 SW 제품 관리자입니다.
    [조회된 문장 리스트]{context}에서 '제품 설명' 부분이 [유사도 비교 문장]{unique_docs}과 SW 의미적으로 관련 없는 경우, 해당 행을 지워주세요.
    조회된 문장 리스트는 제품 설명에 해당하는 metadata를 연결한 제품 정보 데이터 리스트입니다.
    결과는 아래 json 형식으로 변환해서 응답하세요. json 결과만 답변해주세요.
    
    [판단 기준]
    - SW 제품에 대한 설명으로 판단하여 의미적으로 관련 있다는 것은 핵심 기술이나 목적이 동일하거나 매우 유사한 경우를 의미합니다.
    - 관련 없다는 것은 핵심 기술이나 목적이 전혀 다르거나 일치하지 않는 경우입니다.
    
    [예시]
    - 사용자 질의 문장: "DB 보안 제품"
    - 관련 있는 제품 설명:
    - "데이터베이스 암복호화 솔루션"
    - "DB 접근 제어 시스템"
    - 관련 없는 제품 설명:
    - "클라우드 데이터 백업 서비스"
    - "네트워크 모니터링 시스템"

    [반드시 지켜야 하는 출력 형식(json) 예시]
    [
      'result': [
      {{
        'a1': "일련번호 데이터",
        'a2': "인증번호 데이터",
        'a3': "인증일자 데이터",
        'a4': "회사명 데이터",
        'a5': "제품 데이터",
        'a6': "등급 데이터",
        'a7': "시험번호 데이터",
        'a8': "S/W분류 데이터",
        'a9': "제품 설명 데이터",
        'a10': "총WD 데이터",
        'a11': "재계약 데이터",
        'a12': "특이사항 데이터",
        'a13': "시작날짜 데이터 ~ 종료날짜 데이터",
        'a14': "시험원 데이터"
      }},
      ...
      ]
    ]
    """
    
    print("[STEP 2] GPT 요청 시작")
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        print(response)
        # JSON으로 파싱
        response_json = json.loads(response.choices[0].message.content.strip())
        print("[STEP 4] GPT 응답 완료")
        print(response_json)
        return response_json.get("result", [])
    except Exception as e:
        print("[ERROR] GPT 응답 실패:", e)
        return "❌ GPT 응답 생성 중 오류가 발생했습니다."
