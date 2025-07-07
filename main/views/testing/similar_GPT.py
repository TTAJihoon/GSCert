from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def run_openai_GPT(query, persist_path="./main/data/chroma_db", top_k=1):
    print("[STEP 1] 질문 수신:", query)
    
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    db = Chroma(persist_directory=persist_path, embedding_function=embedding)

    print("[STEP 2] Chroma DB 연결 성공")

    try:
        similar_docs = db.similarity_search(query, k=top_k)
        print(f"[STEP 3] 유사 문서 {len(similar_docs)}건 검색됨")
    except Exception as e:
        print("[ERROR] similarity_search 중 오류 발생:", e)

    context = ""
    for i, doc in enumerate(similar_docs):
        meta = doc.metadata
        context += f"[유사도 {i+1}]\n"
        for key, val in meta.items():
            context += f"{key}: {val}\n"
        context += "\n"

    print("[STEP 4] 프롬프트 생성 완료. 길이:", len(context))

    prompt = f"""
    [질문]
    {query}
    
    [유사한 제품 정보]
    {context}
    
    위 내용을 바탕으로 사용자의 질문에 답변해주세요.
    """

    print("[STEP 5] GPT 호출 시작")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    print("[STEP 6] GPT 응답 수신 완료")

    return response.choices[0].message.content
