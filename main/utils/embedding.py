import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import os

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
EMBEDDING_FILE = "embeddings.npy"
TEXT_FILE = "description_texts.csv"


def generate_and_save_embeddings(text_list: list[str], model_name=MODEL_NAME):
    """텍스트 리스트를 임베딩하고 저장 (.npy, .csv)"""
    print("[모델 로딩 중]")
    model = SentenceTransformer(model_name)

    print(f"[임베딩 중] 총 {len(text_list)}건")
    embeddings = model.encode(text_list, convert_to_tensor=False)

    np.save(EMBEDDING_FILE, embeddings)
    pd.DataFrame({"제품 설명": text_list}).to_csv(TEXT_FILE, index=False)
    print(f"[저장 완료] → {EMBEDDING_FILE}, {TEXT_FILE}")


def load_embeddings():
    """저장된 임베딩 및 설명 텍스트 불러오기"""
    if not os.path.exists(EMBEDDING_FILE) or not os.path.exists(TEXT_FILE):
        raise FileNotFoundError("임베딩 파일 또는 텍스트 파일이 존재하지 않습니다.")

    print("[저장된 임베딩 불러오는 중]")
    embeddings = np.load(EMBEDDING_FILE)
    df_text = pd.read_csv(TEXT_FILE)
    return df_text["제품 설명"].tolist(), embeddings
