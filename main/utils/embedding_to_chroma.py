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
        return str(value)[:512]  # 너무 긴 문자열도 잘라줌
    except Exception:
        return ""


def build_chroma_from_csv(csv_path):
    print("[INFO] REFERENCE_DF reloading.")
    print(f"▶ CSV 파일: {csv_path}")

    # STEP 1. CSV 로딩
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # STEP 2. 설명 컬럼 찾기
    desc_col = next((col for col in df.columns if col.strip() in ["제품 설명", "설명", "description"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    # STEP 3. Document 생성
    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="[STEP 3] 임베딩 중..."):
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

    # STEP 4. Chroma DB 경로 설정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(base_dir, "data", "chroma_db")
    os.makedirs(chroma_path, exist_ok=True)

    # STEP 5. 임베딩 모델 로딩
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    print("[STEP 6] 빈 Chroma DB 인스턴스 생성")
    db = Chroma(
        persist_directory=chroma_path,
        embedding_function=embedding,
        collection_name="reference_products"
    )
    print("[DEBUG] 문서 0 상세 확인:")
    print("page_content:", docs[0].page_content)
    print("metadata:")
    
    for k, v in docs[0].metadata.items():
        print(f"  {k} ({type(v)}): {repr(v)}")
    
    print("[STEP 7] 문서별 개별 추가 시작")
    for i, doc in enumerate(docs[:100]):  # 100개만 먼저 시도
        try:
            db.add_documents([doc])
            print(f"[OK] 문서 {i} 추가 성공")
        except Exception as e:
            print(f"[❌ ERROR] 문서 {i} 추가 실패: {e}")
            print("→ 해당 metadata:", doc.metadata)
            break

    print("[STEP 8] 저장 시도")
    try:
        db.persist()
        print("✅ 저장 완료")
    except Exception as e:
        print("[❌ ERROR] 저장 중 문제 발생:", e)
