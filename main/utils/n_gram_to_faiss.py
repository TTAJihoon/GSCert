import sqlite3, os, math, numpy as np
from collections import Counter
from kiwipiepy import Kiwi
from sentence_transformers import SentenceTransformer

OUT_NPZ   = "main/data/ngram_table.npz"
MODEL     = "upskyy/bge-m3-korean"

kiwi = Kiwi()
enc  = SentenceTransformer(MODEL)

def fetch_texts(db_path):
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    cur.execute("SELECT 제품설명 FROM sw_data WHERE 시작일자 >= '2016-01-01'")
    rows = cur.fetchall()
    conn.close()
    return [ (r[0] or "").strip() for r in rows if r[0] ]

def kiwi_noun_tokens(s: str):
    toks = []
    for t in kiwi.tokenize(s):
        if t.tag.startswith("NN"):
            toks.append(t.lemma if t.lemma else t.form)
    return [w for w in toks if len(w) >= 2]

def build_ngram_table(db_path):
    min_df=2
    max_df_ratio=0.30
    min_pmi=3.0
  
    texts = fetch_texts(db_path)
    N = len(texts)
    max_df = int(N * max_df_ratio)

    # 1) DF/CF (명사 uni/bi-gram)
    DF = Counter(); CF_uni = Counter(); CF_bi = Counter()
    for s in texts:
        toks = kiwi_noun_tokens(s)
        unis = toks
        bis  = [f"{toks[i]} {toks[i+1]}" for i in range(len(toks)-1)]
        DF.update(set(unis)); DF.update(set(bis))
        CF_uni.update(unis);  CF_bi.update(bis)

    # 2) PMI (bi-gram 결속도)
    total_uni = sum(CF_uni.values()) + 1e-9
    PMI = {}
    for b, cb in CF_bi.items():
        if cb < 2: continue
        w1, w2 = b.split()
        PMI[b] = math.log2((cb * total_uni) / (CF_uni[w1] * CF_uni[w2] + 1e-9))

    # 3) 후보 필터 + IDF
    vocab, idf = [], []
    def _idf(df): return math.log((N+1)/(df+1)) + 1.0
    for g, df in DF.items():
        if df < min_df or df > max_df: continue
        if " " in g and PMI.get(g, 0.0) < min_pmi: continue
        vocab.append(g); idf.append(_idf(df))

    # 4) n-gram 임베딩 + generic centroid
    V = enc.encode(vocab, normalize_embeddings=True).astype("float32")
    df_sorted = sorted(DF.items(), key=lambda x: -x[1])
    base_terms = [g for g,_ in df_sorted[: min(800, len(df_sorted))] if g in set(vocab)]
    if base_terms:
        G = enc.encode(base_terms, normalize_embeddings=True).astype("float32")
        v_generic = G.mean(axis=0); v_generic /= (np.linalg.norm(v_generic)+1e-9)
    else:
        v_generic = np.zeros(V.shape[1], dtype="float32")

    os.makedirs(os.path.dirname(OUT_NPZ), exist_ok=True)
    np.savez(OUT_NPZ,
             vocab=np.array(vocab, dtype=object),
             idf=np.array(idf, dtype="float32"),
             vectors=V,
             generic_centroid=v_generic)
    print(f"[OK] n-gram table saved → {OUT_NPZ} (vocab={len(vocab)})")
