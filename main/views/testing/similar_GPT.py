import os
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
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
        doc_start = datetime.fromisoformat(doc_start) if doc_start else None
        doc_end = datetime.fromisoformat(doc_end) if doc_end else None
        query_start = datetime.fromisoformat(query_start)
        query_end = datetime.fromisoformat(query_end)
        print(doc_start, doc_end, query_start, query_end)

        if doc_start and query_start <= doc_start <= query_end:
            return True
        if doc_end and query_start <= doc_end <= query_end:
            return True
        if doc_start and doc_end and doc_start <= query_start and doc_end >= query_end:
            return True
    except:
        pass
    return False
    
def get_paraphrased_queries(query: str, num: int) -> list[str]:
    system_prompt = (
        f"다음 문장을 의미가 같도록 다른 표현으로 {num}개 만들어줘.\n"
        f"원문: '{query}'"
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
        paraphrased = [line.strip("1234567890. ").strip() for line in raw_text.split("\n") if line.strip()]
        return paraphrased[:num]
    except Exception as e:
        print("[ERROR] GPT 파라프레이즈 실패:", e)
        return [query]

def run_openai_GPT(query, start, end, top_k=10):
    print("[STEP 1] 사용자 질문 수신:", query)

    # STEP 1. GPT를 사용해 질의 파라프레이즈 생성
    sub_queries = get_paraphrased_queries(query, num=5)
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
    print(unique_docs)

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

    prompt = f"""
[사용자 질문]
{query}

[GPT가 생성한 파라프레이즈 질의]
{sub_queries}

[유사 문서 정보]
{context}

→ 결과 비교를 위해 전달 받은 제품명 및 제품 정보를 모두 표시한 후, 이 문서들 중에서 의미적으로 유사하지 않다고 판다되는 제품은 지워줘
→ 그리고 API를 통해 총 몇 token을 주고 받았는지도 알려줘. 요금 계산을 위한 정보가 필요해.
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
