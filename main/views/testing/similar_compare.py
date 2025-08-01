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
  if indices:
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
  db_ids = np.load("man/data/db_ids.npy")  # DB에서 SELECT한 실제 id들

  model = SentenceTransformer("upskyy/bge-m3-korean")
  query_vec = model.encode([text], normalize_embeddings=True).astype('float32')

  D, I = index.search(query_vec, k=30)

  matched_db_ids = db_ids[I[0]]
  tables = select_data_from_db(matched_db_ids)[::-1]
  print("가장 유사한 DB id:", matched_db_ids)

  return tables 
