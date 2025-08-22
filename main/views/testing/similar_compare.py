import faiss
import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer

def select_data_from_db(indices):
  conn = sqlite3.connect("main/data/reference.db")
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()

  query = "SELECT * FROM sw_data WHERE "
  params = []
  if len(indices) > 0:
    placeholders = ','.join('?' for _ in indices)
    query += f" 일련번호 IN ({placeholders})"
    params.extend(indices)

  cursor.execute(query, params)
  rows = cursor.fetchall()
  result = [dict(row) for row in rows]
  conn.close()
  return result

def _load_ngram_assets(path="main/data/ngram_table.npz"):
    dat = np.load(path, allow_pickle=True)
    vocab = dat["vocab"].tolist()
    idf   = dat["idf"].astype("float32")
    V_ng  = dat["vectors"].astype("float32")
    v_gen = dat["generic_centroid"].astype("float32")
    return vocab, idf, V_ng, v_gen

def _pick_anchors(qv, vocab, idf, V_ng, v_gen, topk_vocab=12, num_anchors=2):
    # anchor_score = α·cos(q,g) + β·IDF − γ·cos(generic,g) + δ·cos(cohesion,g)
    sims = V_ng @ qv
    idx  = sims.argsort()[-topk_vocab:][::-1]
    cand_v = V_ng[idx]; cand_idf = idf[idx]
    coh = cand_v.mean(axis=0); coh /= (np.linalg.norm(coh)+1e-9)

    alpha, beta, gamma, delta = 1.0, 0.6, 0.6, 0.3
    score = alpha*sims[idx] + beta*cand_idf - gamma*(cand_v @ v_gen) + delta*(cand_v @ coh)

    order = score.argsort()[::-1]
    anchors_vec = cand_v[order[:num_anchors]]
    anchors_str = [vocab[i] for i in idx[order[:num_anchors]]]
    aux_terms   = [vocab[i] for i in idx[order[num_anchors:]]]
    return anchors_str, anchors_vec, aux_terms

def _softgate_feats(text, cand_vec, anchors_str, anchors_vec):
    exact_hits = sum(1 for a in anchors_str if a in text)  # 문자 일치
    sem_hit = float((anchors_vec @ cand_vec).max()) if len(anchors_vec) else 0.0
    return exact_hits, sem_hit

# 소프트게이트 재랭킹 추가
def compare_from_index(text):
    # 0) 인덱스/ID 로드
    index = faiss.read_index("main/data/faiss_bge_m3_ko.index")
    db_ids = np.load("main/data/db_ids.npy", allow_pickle=True)

    # 1) 쿼리 임베딩
    model = SentenceTransformer("upskyy/bge-m3-korean")
    query_vec = model.encode([text], normalize_embeddings=True).astype('float32')

    # 2) 1차 검색 (상위 30)
    D, I = index.search(query_vec, k=30)         # D=inner product(=cosine), I=인덱스(0..N-1)
    faiss_idx = I[0]
    base_sims = D[0].tolist()                    # 그대로 코사인 유사도

    # 3) 매칭된 DB id로 원문 조회
    matched_db_ids = [int(db_ids[i]) for i in faiss_idx]
    tables_unsorted = select_data_from_db(matched_db_ids)

    # 4) id → row 매핑 (원래 순서를 유지하려고)
    id_to_table = {item['일련번호']: item for item in tables_unsorted}
    tables = [id_to_table.get(int(db_ids[i]), {}) for i in faiss_idx]

    # 5) n-gram 테이블 로드 → 앵커 추출
    vocab, idf, V_ng, v_gen = _load_ngram_assets("main/data/ngram_table.npz")
    anchors_str, anchors_vec, aux_terms = _pick_anchors(query_vec[0], vocab, idf, V_ng, v_gen,
                                                        topk_vocab=12, num_anchors=2)

    # 6) 후보 벡터 재구성(IndexFlatIP는 reconstruct 지원)
    cand_vecs = np.vstack([ index.reconstruct(int(i)) for i in faiss_idx ]).astype("float32")

    # 7) 소프트게이트 재점수
    #    final = w_emb*base + w_sem*sem + w_lex*log1p(exact) - w_gen*(generic)
    w_emb, w_sem, w_lex, w_gen, w_aux = 1.0, 0.6, 0.4, 0.4, 0.1
    finals = []
    for t, base, v in zip(tables, base_sims, cand_vecs):
        if not t:   # 방어
            finals.append(-1e9); continue
        exact, sem = _softgate_feats(t.get("제품설명",""), v, anchors_str, anchors_vec)
        generic_penalty = float(v @ v_gen)
        aux_hits = sum(1 for a in aux_terms if a in t.get("제품설명",""))
        final = (w_emb*base + w_sem*sem + w_lex*np.log1p(exact) - w_gen*generic_penalty
                 + w_aux*np.log1p(aux_hits))
        t['base_similarity'] = float(base)
        t['anchor_exact_hits'] = int(exact)
        t['anchor_sem_hit'] = float(sem)
        t['aux_hits'] = int(aux_hits)
        t['final_score'] = float(final)
        finals.append(final)

    # 8) 최종 정렬: final_score 내림차순
    tables_sorted = sorted(tables, key=lambda x: x.get('final_score', -1e9), reverse=True)

    return tables_sorted, base_sims
