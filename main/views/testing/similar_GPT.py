import numpy as np
import faiss
import os
import re
import json
from datetime import datetime
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from openai import OpenAI
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# GPT API 초기화
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 임베딩 모델
embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")

# FAISS 인덱스 로드
base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
faiss_path = os.path.join(base_dir, "data", "faiss_index")
db = FAISS.load_local(
    folder_path=faiss_path,
    embeddings=embedding,
    allow_dangerous_deserialization=True
)
faiss_id_to_doc_id = dict(enumerate(db.docstore._dict.keys()))
doc_id_to_faiss_id = {v: k for k, v in faiss_id_to_doc_id.items()}

def is_within_date_range(doc_start, doc_end, query_start, query_end):
    try:
        doc_start = datetime.fromisoformat(doc_start.strip()) if doc_start else None
        doc_end = datetime.fromisoformat(doc_end.strip()) if doc_end else None
        query_start = datetime.fromisoformat(query_start.strip())
        query_end = datetime.fromisoformat(query_end.strip())

        if doc_start and query_start <= doc_start <= query_end:
            return True
        if doc_end and query_start <= doc_end <= query_end:
            return True
        if doc_start and doc_end and doc_start <= query_start and doc_end >= query_end:
            return True
    except Exception as e:
        print("[ERROR] 날짜 필터링에 오류가 발생했습니다:", e)
    return False
    
def get_paraphrased_queries(query: str, num: int) -> list[str]:
    system_prompt = (
        f"""
        아래 입력된 문장과 의미적으로 매우 유사하되, 단어와 표현 방식을 바꾼 문장 {num}개를 제공하세요.
        각 문장 앞에 번호를 붙여 다음 형식으로 제공합니다.

        입력 문장: DB 보안 제품
        출력 문장:
        1. 데이터베이스 암복호화 솔루션
        2. DB 접근제어 소프트웨어
        3. 데이터베이스 보안 관리 시스템

        입력 문장: {query}
        출력 문장:
        """
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "너는 질의어를 다양한 표현으로 바꾸는 도우미야."},
                {"role": "user", "content": system_prompt}
            ]
        )
        raw_text = response.choices[0].message.content
        # 문장만 추출 (숫자, 리스트 제거)
        paraphrased = re.findall(r"\d+\.\s*(.+)", raw_text)
        paraphrased.insert(0, query)
        return paraphrased[:num+1]
    except Exception as e:
        print("[ERROR] GPT 파라프레이즈 실패:", e)
        return [query]

def filter_document_ids_by_date(docstore, start, end):
    filtered_ids = [
        doc_id for doc_id, doc in docstore.items()
        if is_within_date_range(
            doc.metadata.get("시작일자"),
            doc.metadata.get("종료일자"),
            start,
            end
        )
    ]
    return filtered_ids


def search_filtered_vectors(query, filtered_faiss_ids, db, embedding, top_k=15):
    vectors = np.array([db.index.reconstruct(faiss_id) for faiss_id in filtered_faiss_ids])
    temp_index = faiss.IndexFlatL2(vectors.shape[1])
    temp_index.add(vectors)

    query_vector = np.array([embedding.embed_query(query)])
    distances, indices = temp_index.search(query_vector, top_k)
    matched_doc_ids = [faiss_id_to_doc_id[filtered_faiss_ids[idx]] for idx in indices[0]]
    docs = [db.docstore._dict[doc_id] for doc_id in matched_doc_ids]

    return docs
    
def run_openai_GPT(query, start, end, top_k=15): # 문장당 유사제품 검색 개수
    print("[STEP 1] 사용자 질문 수신:", query)

    # STEP 1. GPT를 사용해 질의 파라프레이즈 생성
    sub_queries = get_paraphrased_queries(query, num=3) # 추천 문장 생성 개수
    print("[STEP 1.5] 파라프레이즈 질의:", sub_queries)

    # STEP 2. 날짜로 문서 ID 필터링
    filtered_ids = filter_document_ids_by_date(db.docstore._dict, start, end)
    
    # 필터링 결과 없으면 종료
    if not filtered_ids:
        return "❌ 날짜에 해당하는 문서를 찾지 못했습니다."

    # STEP 3. 유사도 검색 수행 (임시 벡터 기반)
    all_docs = []
    for sq in sub_queries:
        try:
            docs = search_filtered_vectors(sq, filtered_faiss_ids, db, embedding, top_k=top_k)
            print(f"[FAISS] '{sq}' → {len(docs)}건 검색됨")
            all_docs.extend(docs)
        except Exception as e:
            print(f"[ERROR] FAISS 검색 실패 (query: {sq}):", e)

    # STEP 2.5 중복 제거 (by 문서 메타정보 기준)
    seen = set()
    unique_docs = []
    for doc in all_docs:
        uid = doc.metadata.get("인증번호", "") + doc.metadata.get("제품", "")
        if uid not in seen:
            seen.add(uid)
            unique_docs.append(doc)

    print(f"[STEP 2.5] 중복 제거 후 문서 수: {len(unique_docs)}")
    
    if not unique_docs:
        return "❌ 유사한 문서를 찾지 못했습니다."

    # STEP 3. 프롬프트 구성
    context = ""
    for i, doc in enumerate(unique_docs[:top_k]):
        meta = doc.metadata
        context += f"인증번호:{meta.get('인증번호', '')}, "
        context += f"인증일자:{meta.get('인증일자', '')}, "
        context += f"회사명:{meta.get('회사명', '')}, "
        context += f"제품명:{meta.get('제품', '')}, "
        context += f"시험번호:{meta.get('시험번호', '')}, "
        context += f"S/W분류:{meta.get('S_W분류', '')}, "
        context += f"제품 설명:{meta.get('제품_설명', '')}, "
        context += f"총WD:{meta.get('총WD', '')}, "
        context += f"재계약:{meta.get('재계약', '')}, "
        context += f"시작날짜:{meta.get('시작날짜', '')}, "
        context += f"종료날짜:{meta.get('종료날짜', '')}, "
        context += f"시험원:{meta.get('시험원', '')}\n"

    prompt = f"""
    당신은 SW 제품 관리자입니다.
    [조회된 문장 리스트]{context}에서 '제품 설명' 부분이 [사용자 질의 문장]{query}과 SW 의미적으로 관련 없는 경우, 해당 행을 지워주세요.
    조회된 문장 리스트는 제품 설명에 해당하는 metadata를 연결한 제품 정보 데이터 리스트입니다.
    결과는 아래 json 형식으로 변환해서 응답하세요. json 결과만 답변해주세요.
    
    [판단 기준]
    - SW 제품에 대한 설명으로 판단하여 의미적으로 관련 있다는 것은 핵심 기술이나 목적이 동일하거나 매우 유사한 경우를 의미합니다.
    - 관련 없다는 것은 핵심 기술이나 목적이 전혀 다르거나 일치하지 않는 경우입니다.
    
    [예시]
    - 사용자 질의 문장: "DB 보안 제품"
    - 관련 있는 제품 설명:
    - "데이터베이스 암복호화 솔루션"
    - "DB 접근 제어 시스템"
    - 관련 없는 제품 설명:
    - "클라우드 데이터 백업 서비스"
    - "네트워크 모니터링 시스템"

    [반드시 지켜야 하는 출력 형식(json) 예시]
    [
      'result': [
      {{
        'a1': "일련번호 데이터",
        'a2': "인증번호 데이터",
        'a3': "인증일자 데이터",
        'a4': "회사명 데이터",
        'a5': "제품 데이터",
        'a6': "등급 데이터",
        'a7': "시험번호 데이터",
        'a8': "S/W분류 데이터",
        'a9': "제품 설명 데이터",
        'a10': "총WD 데이터",
        'a11': "재계약 데이터",
        'a12': "특이사항 데이터",
        'a13': "시작날짜 데이터 ~ 종료날짜 데이터",
        'a14': "시험원 데이터"
      }},
      ...
      ]
    ]
    """
    
    # STEP 4. GPT 응답 요청
    print("[STEP 3] GPT 요청 시작")

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        print(response)
        # JSON으로 파싱
        response_json = json.loads(response.choices[0].message.content.strip())
        print("[STEP 4] GPT 응답 완료")
        print(response_json)
        return response_json.get("result", [])
    except Exception as e:
        print("[ERROR] GPT 응답 실패:", e)
        return "❌ GPT 응답 생성 중 오류가 발생했습니다."
