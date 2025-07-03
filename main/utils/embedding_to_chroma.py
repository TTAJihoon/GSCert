import pandas as pd
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from tqdm import tqdm
import os

def build_chroma_from_csv(csv_path):
    df = pd.read_csv(csv_path)

    desc_col = next((col for col in df.columns if col.strip() in ["제품 설명", "설명", "description"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="임베딩 중..."):
        description = row.get(desc_col, "")
        if pd.isna(description) or not str(description).strip():
            continue

        docs.append(
            Document(
                page_content=str(description),
                metadata=row.to_dict()
            )
        )

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(base_dir, "data", "chroma_db")

    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    db = Chroma.from_documents(documents=docs, embedding=embedding, persist_directory=chroma_path)
    db.persist()
    print("✅ Chroma 저장 완료 ({}건)".format(len(docs)))
