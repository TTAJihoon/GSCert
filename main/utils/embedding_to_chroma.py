import pandas as pd
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from tqdm import tqdm
import os

def build_chroma_from_csv(csv_path):
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    desc_col = next((col for col in df.columns if col in ["제품 설명", "설명", "description"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="임베딩 중..."):
        description = row.get(desc_col, "")
        if pd.isna(description) or not str(description).strip():
            continue

        # metadata 정제: 모든 값을 str로 변환하고 NaN은 빈 문자열 처리
        clean_metadata = {
            k: "" if pd.isna(v) else str(v)
            for k, v in row.to_dict().items()
        }
        
        docs.append(
            Document(
                page_content=str(description),
                metadata=clean_metadata
            )
        )

    # Chroma 저장 경로 설정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(base_dir, "data", "chroma_db")
    os.makedirs(chroma_path, exist_ok=True)

    print("[STEP 4] Chroma DB 객체 생성 중...")
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    db = Chroma.from_documents(documents=docs, embedding=embedding, persist_directory=chroma_path)

    print("[STEP 5] DB 저장(persist) 중...")
    db.persist()

    print("✅ Chroma 저장 완료. 문서 수:", len(docs))
