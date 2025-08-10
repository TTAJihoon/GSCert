import faiss
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer

def select_data_from_db(indices):
  conn = sqlite3.connect("main/data/reference.db")
  conn.row_factory = sqlite3.Row  # 컬럼명을 사용해서 결과를 가져올 수 있게 설정
  cursor = conn.cursor()

  query = "SELECT * FROM sw_data WHERE "
  params = []

  # 인덱스 리스트가 비어있지 않으면, 쿼리에 조건 추가
  if len(indices) > 0:
    placeholders = ','.join('?' for _ in indices)
    query += f" 일련번호 IN ({placeholders})"
    params.extend(indices)

  # 쿼리 실행
  cursor.execute(query, params)
  rows = cursor.fetchall()

  # 결과를 딕셔너리 형태로 변환
  result = [dict(row) for row in rows]

  conn.close()
  return result

def compare_from_index(text):
    index = faiss.read_index("main/data/faiss_bge_m3_ko.index")
    db_ids = np.load("main/data/db_ids.npy")

    model = SentenceTransformer("upskyy/bge-m3-korean")
    query_vec = model.encode([text], normalize_embeddings=True).astype('float32')

    D, I = index.search(query_vec, k=30)

    matched_db_ids = [int(db_ids[i]) for i in I[0]]

    # DB에서 id들로 조회 (순서는 보장 안 됨)
    tables_unsorted = select_data_from_db(matched_db_ids)

    distances = D[0]
    similarities = 1 - (distances ** 2) / 2
    similarities = similarities.tolist()

    # id->테이블 항목 딕셔너리 생성
    id_to_table = {item['일련번호']: item for item in tables_unsorted}

    # matched_db_ids 순서대로 정렬 (순서 보장)
    tables_sorted = [id_to_table[id_] for id_ in matched_db_ids if id_ in id_to_table]

    # 유사도와 같이 묶어서 각 항목에 유사도 추가
    for table, sim in zip(tables_sorted, similarities):
        table['similarity'] = sim

    print("정렬된 결과:", tables_sorted)
    print("가장 유사한 DB id:", matched_db_ids)
    print("유사도 리스트:", similarities)

    return tables_sorted, similarities
