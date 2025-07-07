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

def run_openai_GPT(query, top_k=3):
    print("[STEP 1] 사용자 질문 수신:", query)

    # 유사 문서 검색
    try:
        docs = db.similarity_search(query, k=top_k)
        print(f"[STEP 2] 유사 문서 {len(docs)}건 검색됨")
    except Exception as e:
        print("[ERROR] FAISS 검색 실패:", e)
        return "❌ 문서 검색 중 오류가 발생했습니다."

    # 프롬프트 구성
    context = ""
    for i, doc in enumerate(docs):
        context += f"[문서 {i+1}]\n"
        for k, v in doc.metadata.items():
            context += f"{k}: {v}\n"
        context += "\n"

    prompt = f"""
[질문]
{query}

[유사한 문서 정보]
{context}

위 내용을 참고하여 사용자의 질문에 대해 설명하거나 추천해주세요.
"""

    print("[STEP 3] GPT 요청 시작")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        print("[STEP 4] GPT 응답 완료")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[ERROR] GPT 응답 실패:", e)
        return "❌ GPT 응답 생성 중 오류가 발생했습니다."
