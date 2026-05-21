import json
import os

from main.utils.gemini_gemma import (
    GemmaConfigError,
    GemmaGenerationError,
    extract_json_object,
    generate_gemma_text,
)

DEFAULT_RERANK_MODEL = "gemini-3.1-flash-lite"


def run_gemini_gemma(query):
    """Gemini API hosted Gemma 모델로 제품 개요를 한 문장으로 요약한다."""
    source_text = "\n".join(query) if isinstance(query, (list, tuple)) else str(query)
    print("[STEP 1] 사용자 질문 수신:", source_text[:500])
    prompt = f"""
    너는 SW 프로그램 매뉴얼 내용을 참고하여 제3자에게 제품을 설명하는 SW 제품 설명 전문가이다.  
    아래 조건에 따라 한 문장의 제품 개요를 100자 미만으로 작성하라.  

    1. 실무적이고 소프트웨어 중심의 톤으로 “~을 지원/제공하는 ~솔루션/시스템/플랫폼/프로그램” 형식으로 작성한다.
    2. 마지막을 끝맺을때는 해당 제품을 가장 잘 설명할 수 있는 단어 1개를 선택하여 추가한다. 예를 들면 쇼핑몰 시스템, DBMS 솔루션 등.
    3. 문장 끝에 추가하는 단어(RAG, LLM, EAI, LMS, DBMS 등)는 입력 문장에 해당 기술명이나 연관 내용이 명확히 포함되어 있을 단어만 문장 끝에 넣는다.
       그렇지 않으면 넣지 않는다.
    4. ‘소프트웨어 솔루션’ 또는 ‘플랫폼 솔루션’ 등 중복/유사 표현은 절대 사용하지 않는다.  
    5. 본 제품명이나 제조사는 반드시 제외한다. 단, 해당 제품과 연동하는 쿠버네티스, AWS 등 연동 제품명은 작성 가능하다.  
    6. 요약 대상 메뉴얼 텍스트에 포함되지 않은 임의의 기술명, 기능, 연관 단어를 추가하지 않는다.  
    7. 오직 매뉴얼에 작성된 내용에만 기반하여 한 문장으로 요약문만 작성하고, 요약문 외에는 어떠한 문구도 제공 금지.
    아래는 요약 대상 매뉴얼 텍스트야:
    \"\"\"{source_text}\"\"\"
    """
    
    print("[STEP 2] Gemini/Gemma 요청 시작")
    try:
        result_text = generate_gemma_text(prompt)
        print("[STEP 3] Gemini/Gemma 응답 완료:", result_text)
        return result_text

    except GemmaConfigError as e:
        print("[ERROR] Gemini/Gemma 설정 오류:", e)
        return f"❌ {e}"
    except GemmaGenerationError as e:
        print("[ERROR] Gemini/Gemma 응답 실패:", e)
        return "❌ Gemma 응답 생성 중 오류가 발생했습니다."


# 기존 import 경로 호환용. 새 코드에서는 run_gemini_gemma를 직접 사용하는 것을 권장한다.
def run_openai_GPT(query):
    return run_gemini_gemma(query)


def _normalize_text(value):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def rerank_similar_candidates(query_text, candidates, top_n=30):
    """FAISS 후보를 LLM으로 재평가하고 상위 후보만 반환한다."""
    candidate_payload = []
    candidate_by_id = {}

    for row in candidates:
        row_id = str(row.get("일련번호", "")).strip()
        description = _normalize_text(row.get("제품설명"))
        if not row_id or not description:
            continue
        candidate_by_id[row_id] = row
        candidate_payload.append(
            {
                "id": row_id,
                "text": description,
            }
        )

    if not candidate_payload:
        return []

    prompt = f"""
너는 소프트웨어 제품 유사도 재평가 전문가다.

사용자 입력 문장과 후보 제품 설명 목록을 비교하여 실제 목적, 핵심 기능, 기술 영역이 가까운 순서로 재정렬하라.

먼저 사용자 입력 문장에서 다음을 내부적으로 판단하라.
1. 핵심 기능
2. 핵심 기술 또는 도메인
3. 반드시 중요하게 봐야 할 표현
4. 일반적이라 같은 단어가 있어도 높은 점수를 주면 안 되는 표현
5. 관련은 있지만 핵심이 아니면 감점해야 하는 표현

평가 기준:
- 핵심 기능과 사용 목적이 직접 일치하면 높게 평가한다.
- 같은 단어가 있어도 목적이 다르면 낮게 평가한다.
- API, 플랫폼, 관리, 데이터, 솔루션, 시스템, 프로그램, 서비스 같은 일반 단어만 겹치는 경우 낮게 평가한다.
- 입력의 핵심 기술어와 후보의 핵심 기능이 맞으면 높게 평가한다.
- 단순 연동 기능, 부가 기능, 저장/관리 기능만 유사하면 낮게 평가한다.

사용자 입력 문장:
{query_text}

후보 목록 JSON:
{json.dumps(candidate_payload, ensure_ascii=False)}

반환 형식:
- 설명 문장, 마크다운, 코드블록 없이 JSON 객체만 반환한다.
- results 배열에는 가장 유사한 상위 {top_n}개만 포함한다.
- score는 0부터 100 사이의 정수다.
- results 배열의 각 항목은 id와 score만 포함한다.

예:
{{
  "results": [
    {{"id": "123", "score": 95}}
  ]
}}
"""

    print("[STEP 4] LLM 유사도 재평가 요청 시작")
    rerank_model = os.environ.get("GEMINI_RERANK_MODEL") or DEFAULT_RERANK_MODEL
    result_text = generate_gemma_text(prompt, model=rerank_model)
    parsed = extract_json_object(result_text)
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list):
        raise GemmaGenerationError("LLM 유사도 재평가 응답 JSON을 해석할 수 없습니다.")

    reranked = []
    seen_ids = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        row_id = str(item.get("id", "")).strip()
        if not row_id or row_id in seen_ids or row_id not in candidate_by_id:
            continue
        try:
            score = max(0, min(100, int(round(float(item.get("score", 0))))))
        except (TypeError, ValueError):
            score = 0

        row = dict(candidate_by_id[row_id])
        row["faiss_similarity"] = float(row.get("similarity") or 0.0)
        row["llm_score"] = score
        row["similarity"] = score / 100
        reranked.append(row)
        seen_ids.add(row_id)
        if len(reranked) >= top_n:
            break

    return reranked
