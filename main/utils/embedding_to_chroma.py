import os
import pandas as pd
from tqdm import tqdm
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

def build_chroma_from_csv(csv_path):
    print("[INFO] REFERENCE_DF reloading.")
    print(f"▶ CSV 파일: {csv_path}")

    # CSV 로딩
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()  # 컬럼 공백 제거

    # 설명 컬럼 찾기
    desc_col = next((col for col in df.columns if col.strip() in ["제품 설명", "설명", "description"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    # 문서 리스트 생성
    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="임베딩 중..."):
        description = row.get(desc_col, "")
        if pd.isna(description) or not str(description).strip():
            continue

        # metadata 정제
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

    # 저장 경로 설정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(base_dir, "data", "chroma_db")
    os.makedirs(chroma_path, exist_ok=True)

    # 임베딩 모델 로딩
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    print("[STEP 4] 빈 Chroma DB 인스턴스 생성")
    db = Chroma(
        embedding_function=embedding,
        persist_directory=chroma_path,
    )

    print("[STEP 4-1] 문서 추가 중...")
    try:
        for i in tqdm(range(0, len(docs), 100), desc="Chroma에 문서 추가"):
            batch = docs[i:i+100]
            db.add_documents(batch)
    except Exception as e:
        print("[ERROR] 문서 추가 중 오류 발생:", e)
        return

    print("[STEP 5] DB 저장 중...")
    try:
        db.persist()
        print("✅ 저장 완료. 총 문서 수:", len(docs))
    except Exception as e:
        print("[ERROR] DB 저장 중 오류 발생:", e)
