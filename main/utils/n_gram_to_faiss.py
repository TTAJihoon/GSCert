import sqlite3, os, math, re, unicodedata, numpy as np
from collections import Counter
from kiwipiepy import Kiwi
from sentence_transformers import SentenceTransformer

OUT_NPZ = "main/data/ngram_table.npz"
MODEL   = "upskyy/bge-m3-korean"

kiwi = Kiwi()
enc  = SentenceTransformer(MODEL)

def _norm_token(s: str) -> str:
    # 유니코드 정규화 + 공백류 제거(스페이스/탭/개행/넓은공백 등)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", "", s)
    return s

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
            lemma = t.lemma if t.lemma else t.form
            tok = _norm_token(lemma)
            if len(tok) >= 2:
                toks.append(tok)
    return toks

def build_ngram_table(db_path):
    min_df = 2
    max_df_ratio = 0.30
    min_pmi = 3.0

    texts = fetch_texts(db_path)
    N = len(texts)
    max_df = int(N * max_df_ratio)

    # 1) DF/CF (명사 uni + bi-gram[튜플])
    DF = Counter()          # 문자열 키: uni("인장"), bi("인장 관리")
    CF_uni = Counter()      # 문자열 키
    CF_bi  = Counter()      # 튜플 키: ("인장","관리")

    for s in texts:
        toks = kiwi_noun_tokens(s)
        # uni
        CF_uni.update(toks)
        DF.update(set(toks))
        # bi (튜플)
        bi_tuples = [(toks[i], toks[i+1]) for i in range(len(toks)-1)]
        CF_bi.update(bi_tuples)
        # DF에는 문자열로 넣어줌(후속 필터에서 " " in g 사용)
        DF.update(set([f"{a} {b}" for (a, b) in bi_tuples]))

    # 2) PMI (bi-gram 결속도) — 튜플을 직접 언패킹
    total_uni = sum(CF_uni.values()) + 1e-9
    PMI = {}  # 문자열 키 "w1 w2" → pmi 값
    for (w1, w2), cb in CF_bi.items():
        if cb < 2:
            continue
        c1, c2 = CF_uni[w1], CF_uni[w2]
        pmi = math.log2((cb * total_uni) / (c1 * c2 + 1e-9))
        PMI[f"{w1} {w2}"] = pmi

    # 3) 후보 필터 + IDF
    vocab, idf = [], []
    def _idf(df): return math.log((N+1)/(df+1)) + 1.0

    for g, df in DF.items():
        if df < min_df or df > max_df:
            continue
        if " " in g and PMI.get(g, 0.0) < min_pmi:
            continue
        vocab.append(g)
        idf.append(_idf(df))

    # 4) n-gram 임베딩 + generic centroid
    if not vocab:
        raise RuntimeError("vocab이 비었습니다. min_df/max_df_ratio/min_pmi 값을 조정해보세요.")
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
