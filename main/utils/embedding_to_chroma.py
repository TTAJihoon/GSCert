import os
import pandas as pd
from tqdm import tqdm
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

def safe_str(value):
    try:
        if pd.isna(value):
            return ""
        return str(value)
    except Exception:
        return ""

def build_chroma_from_csv(csv_path):
    print("[INFO] REFERENCE_DF reloading.")
    print(f"▶ CSV 파일: {csv_path}")

    # STEP 1. CSV 로딩
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # STEP 2. 설명 컬럼 감지
    desc_col = next((col for col in df.columns if col.strip() in ["제품 설명", "설명", "description"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    # STEP 3. Document 리스트 생성
    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="[STEP 3] 임베딩 중..."):
        description = row.get(desc_col, "")
        if pd.isna(description) or not str(description).strip():
            continue

        clean_metadata = {
            str(k).strip(): safe_str(v)
            for k, v in row.to_dict().items()
        }

        docs.append(
            Document(
                page_content=str(description),
                metadata=clean_metadata
            )
        )

    # STEP 4. 저장 경로 설정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(base_dir, "data", "chroma_db")
    os.makedirs(chroma_path, exist_ok=True)

    # STEP 5. 임베딩 모델 로딩
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    print("[STEP 6] 빈 Chroma DB 인스턴스 생성")
    db = Chroma(
        embedding_function=embedding,
        persist_directory=chroma_path,
    )

    # ✅ 여기에 진단용 출력 삽입!
    print("[TEST] 첫 문서 metadata 예시:", docs[0].metadata)
    print("[TEST] 첫 문서 설명 예시:", docs[0].page_content)

    print("[STEP 7] from_documents() 방식으로 전체 추가 중...")
    db = Chroma.from_documents(
        documents=docs,
        embedding=embedding,  # ← ✅ embedding만 전달
        persist_directory=chroma_path,
    )


    print("[STEP 8] DB 저장 중...")
    try:
        db.persist()
        print(f"✅ 저장 완료. 총 문서 수: {len(docs)}")
    except Exception as e:
        print("[ERROR] DB 저장 중 오류 발생:", e)
