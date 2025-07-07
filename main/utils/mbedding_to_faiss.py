import os
import pandas as pd
from tqdm import tqdm
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

def safe_str(value):
    try:
        if pd.isna(value):
            return ""
        v = str(value)
        v = v.replace("\n", "_").replace("\r", "_").replace("\t", "_")
        return v.strip()[:512]
    except Exception:
        return ""

def build_faiss_from_csv(csv_path):
    print("[INFO] CSV 로딩 중...")
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # 설명 컬럼 감지
    desc_col = next((col for col in df.columns if col.strip() in ["제품 설명", "설명", "description"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="[STEP 3] 문서 생성 중"):
        description = row.get(desc_col, "")
        if pd.isna(description) or not str(description).strip():
            continue

        clean_metadata = {
            str(k).strip().replace("\n", "_").replace("/", "_").replace(" ", "_"): safe_str(v)
            for k, v in row.to_dict().items()
        }

        docs.append(
            Document(
                page_content=str(description),
                metadata=clean_metadata
            )
        )

    print("[STEP 4] 임베딩 모델 로딩")
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    print("[STEP 5] FAISS 인덱스 생성 중...")
    db = FAISS.from_documents(docs, embedding)

    print("[STEP 6] FAISS 인덱스 저장 중...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    faiss_path = os.path.join(base_dir, "data", "faiss_index")
    os.makedirs(faiss_path, exist_ok=True)
    db.save_local(faiss_path)

    print("✅ FAISS 저장 완료. 문서 수:", len(docs))
