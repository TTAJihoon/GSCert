from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def ask_question_to_gpt(query, persist_path="./chroma_db", top_k=15): #유사도 기준으로 추출할 문서 수
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    db = Chroma(persist_directory=persist_path, embedding_function=embedding)
    
    similar_docs = db.similarity_search(query, k=top_k)

    context = ""
    for i, doc in enumerate(similar_docs):
        metadata = doc.metadata
        context += f"[유사도 {i+1}]\n"
        for key, value in metadata.items():
            context += f"{key}: {value}\n"
        context += "\n"
    
    prompt = f"""
    사용자 질문: {query}

    아래는 유사한 제품 설명입니다:
    {context}

    위 정보를 바탕으로 답변을 자연스럽게 생성해줘.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content
