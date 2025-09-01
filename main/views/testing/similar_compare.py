import faiss
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer

def select_data_from_db(indices):
    if not indices:
        return []

    conn = sqlite3.connect("main/data/reference.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    placeholders = ','.join('?' for _ in indices)
    query = f"SELECT * FROM sw_data WHERE 일련번호 IN ({placeholders})"
    cursor.execute(query, indices)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def compare_from_index(text, k=30):
    # 1) 인덱스 + 모델 로드
    index = faiss.read_index("main/data/faiss_bge_m3_ko.idmap.index")
    model = SentenceTransformer("upskyy/bge-m3-korean")

    # 2) 쿼리 임베딩
    query_vec = model.encode([text], normalize_embeddings=True).astype('float32')

    # 3) 검색 (D: 유사도(IP), L: 라벨=DB 일련번호)
    D, L = index.search(query_vec, k)

    labels = [int(x) for x in L[0] if x >= 0]
    sims   = [float(x) for x in D[0][:len(labels)]]

    # 4) DB 조회
    tables_unsorted = select_data_from_db(labels)
    id_to_table = {item['일련번호']: item for item in tables_unsorted}
    tables_in_rank = [id_to_table[i] for i in labels if i in id_to_table]

    # 5) similarity 부여
    for tbl, sim in zip(tables_in_rank, sims):
        tbl['similarity'] = sim

    # 6) 🔥 ID 내림차순 정렬
    tables_sorted = sorted(tables_in_rank, key=lambda x: int(x['일련번호']), reverse=True)
    similarities_sorted = [t['similarity'] for t in tables_sorted]

    return tables_sorted, similarities_sorted
