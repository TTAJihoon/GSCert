from main.utils.reload_reference import reload_reference_dataframe, getREF
from sentence_transformers import SentenceTransformer, util
import pandas as pd
import numpy as np
import os

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
EMBEDDING_FILE = "main/data/reference_embeddings.npy"
MODEL = None
EMBEDDINGS = None
EMBEDDED_DF = None
REFERENCE_DF = None

def generate_and_save_embeddings():
    """REFERENCE_DF가 없다면 로딩한 후 임베딩 생성 및 저장"""
    global MODEL

    REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        print("[generate] REFERENCE_DF가 None → reference.csv 로딩 중...")
        reload_reference_dataframe()
        REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        raise ValueError("[generate] REFERENCE_DF is still None. reference.csv 로딩 실패")

    df = REFERENCE_DF[REFERENCE_DF["제품 설명"].notna()].reset_index(drop=True)
    text_list = df["제품 설명"].astype(str).tolist()

    print("[generate] KoSBERT 모델 로딩 중...")
    MODEL = SentenceTransformer(MODEL_NAME)

    print(f"[generate] 총 {len(text_list)}건 임베딩 생성 중...")
    embeddings = MODEL.encode(text_list, convert_to_tensor=False)

    os.makedirs(os.path.dirname(EMBEDDING_FILE), exist_ok=True)
    np.save(EMBEDDING_FILE, embeddings)
    print(f"[generate] 임베딩 저장 완료 → {EMBEDDING_FILE}")


def load_embeddings():
    """임베딩과 참조 DataFrame을 로드하거나 없으면 자동 생성"""
    global MODEL, EMBEDDINGS, EMBEDDED_DF

    print("[load_embeddings] 임베딩 캐시 로딩 시도 중...")

    if not os.path.exists(EMBEDDING_FILE):
        print("[load_embeddings] 임베딩 파일이 없어 생성합니다.")
        generate_and_save_embeddings()

    REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        print("[load_embeddings] REFERENCE_DF가 None → reference.csv 로딩 중...")
        reload_reference_dataframe()
        REFERENCE_DF = getREF()
    if REFERENCE_DF is None:
        raise ValueError("[load_embeddings] REFERENCE_DF is still None. reference.csv 로딩 실패")

    print("[load_embeddings] KoSBERT 모델 로딩 중...")
    MODEL = SentenceTransformer(MODEL_NAME)

    print("[load_embeddings] 임베딩 불러오는 중...")
    EMBEDDINGS = np.load(EMBEDDING_FILE)

    EMBEDDED_DF = REFERENCE_DF[REFERENCE_DF["제품 설명"].notna()].reset_index(drop=True)
    print(f"[load_embeddings] 완료: 임베딩 {len(EMBEDDINGS)}개, 참조 데이터 {len(EMBEDDED_DF)}개 로드 완료")



def search_similar_by_text(query_text: str, top_k: int = 5):
    """입력 문장을 기준으로 의미 유사한 제품 정보 검색"""
    if MODEL is None or EMBEDDINGS is None or EMBEDDED_DF is None:
        raise RuntimeError("임베딩이 로딩되지 않았습니다. 먼저 load_embeddings()를 실행하세요")

    print(f"\n[입력 질의] {query_text[:100]}...")
    query_embedding = MODEL.encode(query_text, convert_to_tensor=True)
    hits = util.semantic_search(query_embedding, EMBEDDINGS, top_k=top_k)[0]

    print(f"\n[유사 제품 Top {top_k}]")
    for i, hit in enumerate(hits):
        idx = hit['corpus_id']
        score = hit['score']
        row = EMBEDDED_DF.iloc[idx]
        print(f"{i+1}. (유사도 {score:.4f}) → 일련번호: {row['일련번호']}, 회사명: {row['회사명']}, 제품: {row['제품']}")
        print(f"    설명: {row['제품 설명'][:100]}...")


def search_similar_by_company(company: str, top_k: int = 5):
    """특정 회사의 최근 인증 제품 설명을 기준으로 유사 제품 검색"""
    if REFERENCE_DF is None:
        reload_reference_dataframe()
    if REFERENCE_DF is None:
        raise ValueError("REFERENCE_DF is still None. reference.csv 로딩 실패")

    df = REFERENCE_DF
    df_filtered = df[df["회사명"].astype(str).str.contains(company, case=False, na=False)]

    if df_filtered.empty:
        raise ValueError(f"[오류] '{company}' 기업명을 포함하는 인증 제품이 없습니다.")

    row = df_filtered.sort_values("인증일자", ascending=False).iloc[0]
    query = str(row["제품 설명"])
    print(f"\n[기준 기업: {company}] 기준 제품 설명: {query[:100]}...")

    search_similar_by_text(query, top_k=top_k)
