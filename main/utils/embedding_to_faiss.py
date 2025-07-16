import os
import re
import pickle
import pandas as pd
from datetime import datetime
from tqdm import tqdm
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

def safe_str(value):
    try:
        if pd.isna(value):
            return ""
        v = str(value)
        v = v.replace("\n", "_").replace("\r", "_").replace("\t", "_")
        return v.strip()[:512]
    except Exception:
        return ""

def parse_korean_date_range(text: str):
    """
    다양한 날짜 포맷(예: '2020년 1월 1일 ~ 2020년 2월 1일', '2020.1.1~2020.2.1')을
    ISO8601 형식의 시작일자와 종료일자로 파싱
    """
    try:
        text = re.sub(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", r"\1.\2.\3", text)
        text = text.replace(" ", "")  # 공백 제거
        text = text.replace("~", " ~ ")  # 파싱 안정성 확보
        dates = re.findall(r"\d{4}\.\d{1,2}\.\d{1,2}", text)
        if len(dates) == 2:
            start = datetime.strptime(dates[0], "%Y.%m.%d").date().isoformat()
            end = datetime.strptime(dates[1], "%Y.%m.%d").date().isoformat()
            return start, end
    except Exception:
        pass
    return None, None

def build_faiss_from_csv(csv_path):
    print("[INFO] CSV 로딩 중...")
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # 설명 컬럼 감지
    desc_col = next((col for col in df.columns if col in ["제품 설명", "설명"]), None)
    if not desc_col:
        raise ValueError("❌ '제품 설명'에 해당하는 컬럼이 없습니다.")

    docs = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="[STEP 3] 문서 생성 중"):
        description = row.get(desc_col, "")
        if pd.isna(description) or not str(description).strip():
            continue

        # 날짜 필드 감지
        raw_date = row.get("시작날짜/\n종료날짜", "")
        start, end = parse_korean_date_range(str(raw_date))

        # 메타데이터 정리
        clean_metadata = {
            str(k).strip().replace("\n", "_").replace("/", "_").replace(" ", "_"): safe_str(v)
            for k, v in row.to_dict().items()
            if k not in ["시작날짜/\n종료날짜"]
        }
        clean_metadata["시작일자"] = start or ""
        clean_metadata["종료일자"] = end or ""

        docs.append(
            Document(
                page_content=str(description),
                metadata=clean_metadata
            )
        )

    print("[STEP 4] 임베딩 모델 로딩")
    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

    print("[STEP 5] FAISS 인덱스 생성 중...")
    
    # 최초 FAISS 인덱스 생성 (한번만!)
    db = FAISS.from_documents(docs, embedding)

    # 저장할 경로 지정 (반드시 절대 경로 추천)
    base_dir = "C:/GSCert/myproject"
    faiss_path = os.path.join(base_dir, "data", "faiss_index")

    print("[STEP 6] FAISS 인덱스 저장 중...")
    #FAISS 인덱스 저장
    db.save_local("faiss_index")
    
    # 문서 ID를 생성한 FAISS 인덱스의 순서대로 저장 (필수!!)
    doc_ids = [doc.metadata["문서ID"] for doc in documents]
    with open(os.path.join(faiss_path, "doc_ids.pkl"), "wb") as f:
        pickle.dump(doc_ids, f)
    
    print("✅ FAISS 저장 완료. 문서 수:", len(docs))
