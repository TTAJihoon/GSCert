import os
import re
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

# 임베딩 모델
embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

# FAISS 인덱스 로드
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
faiss_path = os.path.join(base_dir, "data", "faiss_index")
db = FAISS.load_local(
    folder_path=faiss_path,
    embeddings=embedding,
    allow_dangerous_deserialization=True
)

def is_within_date_range(doc_start, doc_end, query_start, query_end):
    try:
        doc_start = datetime.fromisoformat(doc_start.strip()) if doc_start else None
        doc_end = datetime.fromisoformat(doc_end.strip()) if doc_end else None
        query_start = datetime.fromisoformat(query_start.strip())
        query_end = datetime.fromisoformat(query_end.strip())

        if doc_start and query_start <= doc_start <= query_end:
            return True
        if doc_end and query_start <= doc_end <= query_end:
            return True
        if doc_start and doc_end and doc_start <= query_start and doc_end >= query_end:
            return True
    except Exception as e:
        print("[ERROR] 날짜 필터링에 오류가 발생했습니다:", e)
    return False
    
def get_paraphrased_queries(query: str, num: int) -> list[str]:
    system_prompt = (
        f"""
        아래 입력된 문장과 의미적으로 매우 유사하되, 단어와 표현 방식을 바꾼 문장 {num}개를 제공하세요.
        각 문장 앞에 번호를 붙여 다음 형식으로 제공합니다.

        입력 문장: DB 보안 제품
        출력 문장:
        1. 데이터베이스 암복호화 솔루션
        2. DB 접근제어 소프트웨어
        3. 데이터베이스 보안 관리 시스템

        입력 문장: {query}
        출력 문장:
        """
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "너는 질의어를 다양한 표현으로 바꾸는 도우미야."},
                {"role": "user", "content": system_prompt}
            ]
        )
        raw_text = response.choices[0].message.content
        # 문장만 추출 (숫자, 리스트 제거)
        paraphrased = re.findall(r"\d+\.\s*(.+)", raw_text)
        return paraphrased[:num]
    except Exception as e:
        print("[ERROR] GPT 파라프레이즈 실패:", e)
        return [query]

def run_openai_GPT(query, start, end, top_k=15): # 문장당 유사제품 검색 개수
    print("[STEP 1] 사용자 질문 수신:", query)

    # STEP 1. GPT를 사용해 질의 파라프레이즈 생성
    sub_queries = get_paraphrased_queries(query, num=3) # 추천 문장 생성 개수
    print("[STEP 1.5] 파라프레이즈 질의:", sub_queries)

    # STEP 2. FAISS 유사 문서 검색
    all_docs = db.docstore._dict.values()
    
    # 날짜로 필터링한 문서만 추출
    filtered_docs = [
        doc for doc in all_docs
        if is_within_date_range(
            doc.metadata.get("시작일자"),
            doc.metadata.get("종료일자"),
            start,
            end
        )
    ]

    # 필터링 후 문서가 없는 경우
    if not filtered_docs:
        return "❌ 날짜에 해당하는 문서를 찾지 못했습니다."

    # 필터링한 문서로만 임시 FAISS 인덱스 생성
    temp_db = FAISS.from_documents(filtered_docs, embedding)
    
    all_docs = []
    for sq in sub_queries:
        try:
            docs = temp_db.similarity_search(sq, k=top_k)
            print(f"[FAISS] '{sq}' → {len(docs)}건 검색됨")
            all_docs.extend(docs)
        except Exception as e:
            print(f"[ERROR] FAISS 검색 실패 (query: {sq}):", e)

    # STEP 2.5 중복 제거 (by 문서 메타정보 기준)
    seen = set()
    unique_docs = []
    for doc in all_docs:
        uid = doc.metadata.get("인증번호", "") + doc.metadata.get("제품", "")
        if uid not in seen:
            seen.add(uid)
            unique_docs.append(doc)

    print(f"[STEP 2.5] 중복 제거 후 문서 수: {len(unique_docs)}")
    
    if not unique_docs:
        return "❌ 유사한 문서를 찾지 못했습니다."

    # STEP 3. 프롬프트 구성
    context = ""
    for i, doc in enumerate(unique_docs[:top_k]):
        meta = doc.metadata
        context += f"인증번호:{meta.get('인증번호', '')}, "
        context += f"인증일자:{meta.get('인증일자', '')}, "
        context += f"회사명:{meta.get('회사명', '')}, "
        context += f"제품명:{meta.get('제품', '')}, "
        context += f"시험번호:{meta.get('시험번호', '')}, "
        context += f"S/W분류:{meta.get('S_W분류', '')}, "
        context += f"제품 설명:{meta.get('제품_설명', '')}, "
        context += f"총WD:{meta.get('총WD', '')}, "
        context += f"재계약:{meta.get('재계약', '')}, "
        context += f"시작날짜:{meta.get('시작날짜', '')}, "
        context += f"종료날짜:{meta.get('종료날짜', '')}, "
        context += f"시험원:{meta.get('시험원', '')}\n"
    print(context)

    prompt = f"""
    조회된 문장 리스트: {context}는 사용자가 입력한 원본 문장: {query}으로 생성한 유사도 검색용 문장: {sub_queries}에 대한 조회결과 리스트입니다.  
    리스트에 포함된 문장 중 원본 문장과 의미적으로 관련 없는 문장을 제거하여 조회된 문장 리스트를 출력하세요.
    조회된 문장에는 회사명과 제품명, 제품 설명 3가지를 꼭 포함하여 출력하세요.
    
    [판단 기준]
    - SW 제품에 대한 설명으로 판단하여 의미적으로 관련 있다는 것은 핵심 기술이나 목적이 동일하거나 매우 유사한 경우를 의미합니다.
    - 관련 없다는 것은 핵심 기술이나 목적이 전혀 다르거나 일치하지 않는 경우입니다.
    
    [예시]
    - 원본 문장: "DB 보안 제품"
    - 관련 있는 문장:
    - "데이터베이스 암복호화 솔루션"
    - "DB 접근 제어 시스템"
    - 관련 없는 문장:
    - "클라우드 데이터 백업 서비스"
    - "네트워크 모니터링 시스템"
    
    ---
    
    [출력 형식 예시]
    
    의미적으로 관련 없는 문장을 제거하기 전 전체 조회된 문장 리스트:
    1. [조회된 문장 1]
    2. [조회된 문장 2]
    3. [조회된 문장 3]
    (마지막 문장까지 반복...)
    
    ---
    
    전체 조회된 문장 리스트에서 의미적으로 관련이 없다고 판단되는 문장 번호만 추출하여 아래와 같은 형식으로 출력하세요.
    관련 없는 문장
    5. [관련 없다고 판단한 사유]
    12. [관련 없다고 판단한 사유]
    24. [관련 없다고 판단한 사유]
    (마지막 문장 번호까지 반복...)
    
    """
    
    # STEP 4. GPT 응답 요청
    print("[STEP 3] GPT 요청 시작")

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}]
        )
        print("[STEP 4] GPT 응답 완료")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[ERROR] GPT 응답 실패:", e)
        return "❌ GPT 응답 생성 중 오류가 발생했습니다."
