import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

# (1) SQLite에서 데이터 조회하기
def fetch_texts_from_sqlite(db_path, table_name, text_column):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(f"SELECT id, {text_column} FROM {table_name} WHERE 시작일자 >= '2016-01-01'")
    rows = cursor.fetchall()
    
    conn.close()
    
    ids = [row[0] for row in rows]
    texts = [row[1] for row in rows]
    
    return ids, texts
    
def build_faiss_from_db(db_path):
    # (2) BGE-m3-ko 임베딩 모델 로드하기
    model_name = "BAAI/bge-m3-ko"
    model = SentenceTransformer(model_name)

    # (3) 데이터 조회 및 임베딩 생성
    table_name = "sw_data"
    text_column = "제품설명"

    ids, texts = fetch_texts_from_sqlite(db_path, table_name, text_column)

    print(f"조회된 텍스트 개수: {len(texts)}")

    # 문장 임베딩 (정규화 적용 추천)
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True)
    embeddings = np.array(embeddings).astype('float32')

    print("임베딩 완료된 벡터 형태:", embeddings.shape)

    # (4) FAISS 인덱스 생성 및 저장 (Flat 방식 예시)
    dim = embeddings.shape[1]

    #Flat 인덱스 생성 (가장 간단한 방식)
    index = faiss.IndexFlatIP(dim)  # 코사인 유사도는 내적(IP)을 활용 (normalize_embeddings=True 필수)

    # FAISS에 임베딩 벡터 추가
    index.add(embeddings)

    print(f"FAISS 인덱스에 저장된 벡터 개수: {index.ntotal}")

    # FAISS 인덱스 저장
    faiss.write_index(index, "faiss_bge_m3_ko.index")

    # 별도로 ID 리스트 저장 (추후 검색 시 id 매핑에 필요)
    np.save("ids.npy", np.array(ids))

    print("FAISS 인덱스 및 ID 리스트 저장 완료")
