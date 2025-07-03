import pandas as pd
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.schema import Document
import os

def build_chroma_from_csv(csv_path):
    df = pd.read_csv(csv_path)
    
    # 임베딩 대상은 '제품 설명', metadata는 나머지 전체 row
    docs = []
    for _, row in df.iterrows():
        docs.append(
            Document(
                page_content=row["제품 설명"],
                metadata=row.to_dict()
            )
        )

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(base_dir, "data", "chroma_db")

    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    db = Chroma.from_documents(documents=docs, embedding=embedding, persist_directory=chroma_path)
    db.persist()
    print("✅ 전체 row metadata 포함 저장 완료")
