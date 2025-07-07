from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
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

    [유사한 제품 정보]
    {context}
    
    위 내용을 바탕으로 사용자의 질문에 답변해주세요.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content
