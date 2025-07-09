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

def get_paraphrased_queries(query: str, num: int = 3) -> list[str]:
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

def run_openai_GPT(query, top_k=3):
    print("[STEP 1] 사용자 질문 수신:", query)

    # STEP 1. GPT를 사용해 질의 파라프레이즈 생성
    sub_queries = get_paraphrased_queries(query, num=3)
    print("[STEP 1.5] 파라프레이즈 질의:", sub_queries)

    # STEP 2. FAISS 유사 문서 검색
    all_docs = []
    for sq in sub_queries:
        try:
            docs = db.similarity_search(sq, k=top_k)
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
        context += f"제품:{meta.get('제품', '')}, "
        context += f"시험번호:{meta.get('시험번호', '')}, "
        context += f"S/W분류:{meta.get('S_W분류', '')}, "
        context += f"제품 설명:{meta.get('제품_설명', '')}, "
        context += f"총WD:{meta.get('총WD', '')}, "
        context += f"재계약:{meta.get('재계약', '')}, "
        context += f"시작날짜/종료날짜:{meta.get('시작날짜__종료날짜', '')}, "
        context += f"시험원:{meta.get('시험원', '')}\n"

    prompt = f"""
[사용자 질문]
{query}

[GPT가 생성한 파라프레이즈 질의]
{sub_queries}

[유사 문서 정보]
{context}

→ 이 문서들 중에서 의미적으로 정말 유사한 제품은 무엇인지 알려줘.
→ 각 제품 설명을 꼭 표시해줘.
"""

    # STEP 4. GPT 응답 요청
    print("[STEP 3] GPT 요청 시작")

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano"
            messages=[{"role": "user", "content": prompt}]
        )
        print("[STEP 4] GPT 응답 완료")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[ERROR] GPT 응답 실패:", e)
        return "❌ GPT 응답 생성 중 오류가 발생했습니다."
