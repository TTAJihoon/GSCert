import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

# (1) SQLite에서 데이터 조회하기
def fetch_texts_from_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 텍스트가 비어있지 않은 것만 가져오는 것을 권장
    cursor.execute("""
        SELECT 일련번호, 제품설명
        FROM sw_data
        WHERE 시작일자 >= '2016-01-01'
          AND 제품설명 IS NOT NULL
          AND TRIM(제품설명) != ''
    """)
    rows = cursor.fetchall()
    conn.close()

    ids   = [row[0] for row in rows]   # DB 실제 PK (일련번호)
    texts = [row[1] for row in rows]   # 임베딩할 문장
    return ids, texts

def build_faiss_from_db(db_path):
    # (2) BGE-m3-ko 임베딩 모델 로드
    model_name = "upskyy/bge-m3-korean"
    model = SentenceTransformer(model_name)

    # (3) 데이터 조회 및 임베딩 생성
    ids, texts = fetch_texts_from_sqlite(db_path)
    print(f"조회된 텍스트 개수: {len(texts)}")

    embeddings = model.encode(
        texts,
        normalize_embeddings=True,     # 코사인 유사도(IP)용 정규화
        batch_size=32,
        show_progress_bar=True
    ).astype('float32')

    print("임베딩 완료된 벡터 형태:", embeddings.shape)

    # (4) IndexIDMap2 사용: 라벨에 DB 실제 id(일련번호)를 저장
    dim = embeddings.shape[1]
    base_index = faiss.IndexFlatIP(dim)          # 코사인=IP(정규화 전제)
    index = faiss.IndexIDMap2(base_index)

    ids_np = np.array(ids, dtype=np.int64)       # 반드시 int64
    index.add_with_ids(embeddings, ids_np)       # ← 여기서 id를 함께 저장!

    faiss.write_index(index, "main/data/faiss_bge_m3_ko.idmap.index")
    print("FAISS 인덱스 저장 완료 (IndexIDMap2):", index.ntotal)

    # ✅ IndexIDMap2 전환 시, ids.npy 같은 매핑 파일은 필요 없습니다.
    # np.save("main/data/ids.npy", np.array(ids))  # (선택) 호환용으로만 유지
