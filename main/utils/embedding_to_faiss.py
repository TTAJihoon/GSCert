import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

# (1) SQLite에서 데이터 조회하기
def fetch_texts_from_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(f"SELECT 일련번호, 제품설명 FROM sw_data WHERE 시작일자 >= '2016-01-01'")
    rows = cursor.fetchall()
    
    conn.close()
    
    ids = [row[0] for row in rows]
    texts = [row[1] for row in rows]
    
    return ids, texts
    
def build_faiss_from_db(db_path):
    # (2) BGE-m3-ko 임베딩 모델 로드하기
    model_name = "upskyy/bge-m3-korean"
    model = SentenceTransformer(model_name)

    # (3) 데이터 조회 및 임베딩 생성
    ids, texts = fetch_texts_from_sqlite(db_path)

    print(f"조회된 텍스트 개수: {len(texts)}")

    # 문장 임베딩 (정규화 적용 추천)
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True)
    embeddings = np.array(embeddings).astype('float32')

    print("임베딩 완료된 벡터 형태:", embeddings.shape)

    # (4) 인덱스 생성 및 저장 (IndexIDMap2 사용)
    dim = embeddings.shape[1]
    base_index = faiss.IndexFlatIP(dim)
    index = faiss.IndexIDMap2(base_index)

    # ids 배열을 int64로 맞춰서 DB id와 함께 저장
    ids_np = np.array(ids, dtype=np.int64)
    index.add_with_ids(embeddings, ids_np)

    faiss.write_index(index, "main/data/faiss_bge_m3_ko.idmap.index")
    print("FAISS 인덱스 저장 완료 (IndexIDMap2)")

    # 별도로 ID 리스트 저장 (추후 검색 시 id 매핑에 필요)
    np.save("main/data/ids.npy", np.array(ids))

    print("FAISS 인덱스 및 ID 리스트 저장 완료")
