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
def compare_from_index(text, topM=100, topk=30,
                       hard_gate=False, tau=0.50,
                       # base 가중치를 0으로 ↓↓↓
                       w_emb=0.0, w_sem=0.8, w_lex=0.6, w_gen=0.4, w_aux=0.1):
    index = faiss.read_index("main/data/faiss_bge_m3_ko.index")
    db_ids = np.load("main/data/db_ids.npy", allow_pickle=True)
    model = SentenceTransformer("upskyy/bge-m3-korean")
    qv = model.encode([text], normalize_embeddings=True).astype('float32')

    # D(점수)는 버려도 됨. I(인덱스)는 필요.
    _, I = index.search(qv, k=topM)
    faiss_idx = I[0]

    matched_db_ids = [int(db_ids[i]) for i in faiss_idx]
    rows = select_data_from_db(matched_db_ids)
    id2row = {r['일련번호']: r for r in rows}
    tables = [id2row.get(int(db_ids[i]), {}) for i in faiss_idx]

    # n-gram 로드 & 앵커
    vocab, idf, V_ng, v_gen = _load_ngram_assets("main/data/ngram_table.npz")
    anchors_str, anchors_vec, aux_terms = _pick_anchors(qv[0], vocab, idf, V_ng, v_gen,
                                                        topk_vocab=12, num_anchors=2)

    # 후보 벡터 재구성
    cand_vecs = np.vstack([ index.reconstruct(int(i)) for i in faiss_idx ]).astype("float32")

    scored = []
    for t, v in zip(tables, cand_vecs):
        if not t:
            continue
        exact, sem = _softgate_feats(t.get("제품설명",""), v, anchors_str, anchors_vec)
        if hard_gate and (exact == 0 and sem < tau):
            continue
        generic_penalty = float(v @ v_gen)
        aux_hits = sum(1 for a in aux_terms if _contains_anchor(t.get("제품설명",""), a))

        # ★ base를 쓰지 않음: w_emb=0.0
        final = (w_sem*sem + w_lex*np.log1p(exact)
                 - w_gen*generic_penalty + w_aux*np.log1p(aux_hits))

        t['final_score'] = float(final)
        t['anchor_exact_hits'] = int(exact)
        t['anchor_sem_hit'] = float(sem)
        t['aux_hits'] = int(aux_hits)
        scored.append(t)

    tables_sorted = sorted(scored, key=lambda x: x['final_score'], reverse=True)[:topk]
    final_scores  = [t['final_score'] for t in tables_sorted]
    return tables_sorted, final_scores
