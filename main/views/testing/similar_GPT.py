from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def run_openai_GPT(query, persist_path="./main/data/chroma_db", top_k=15):
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    db = Chroma(persist_directory=persist_path, embedding_function=embedding)
    
    similar_docs = db.similarity_search(query, k=top_k)
    
    context = ""
    for i, doc in enumerate(similar_docs):
        meta = doc.metadata
        context += f"[유사도 {i+1}]\n"
        for key, val in meta.items():
            context += f"{key}: {val}\n"
        context += "\n"

    prompt = f"""
    [질문]
    {query}
    
    [유사한 제품 정보]
    {context}
    
    위 내용을 바탕으로 사용자의 질문에 답변해주세요.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content.strip()
