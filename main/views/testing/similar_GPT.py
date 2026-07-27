import json
import logging
import os

from main.utils.gemini_gemma import (
    GemmaConfigError,
    GemmaGenerationError,
    extract_json_object,
    generate_gemma_text,
)

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "gemini-3.1-flash-lite"


def run_gemini_gemma(query):
    """Gemini API hosted Gemma 모델로 제품 개요를 한 문장으로 요약한다."""
    source_text = "\n".join(query) if isinstance(query, (list, tuple)) else str(query)
    logger.debug("Gemini/Gemma summary input: %s", source_text[:500])
    prompt = f"""
    너는 SW 프로그램 매뉴얼 내용을 참고하여 제3자에게 제품을 설명하는 SW 제품 설명 전문가이다.
    아래 조건에 따라 한 문장의 제품 개요를 100자 미만으로 작성하라.

    1. 실무적이고 소프트웨어 중심의 톤으로 "~을 지원/제공하는 ~솔루션/시스템/플랫폼/프로그램" 형식으로 작성한다.
    2. 마지막을 끝맺을때는 해당 제품을 가장 잘 설명할 수 있는 단어 1개를 선택하여 추가한다. 예를 들면 쇼핑몰 시스템, DBMS 솔루션 등.
    3. 문장 끝에 추가하는 단어(RAG, LLM, EAI, LMS, DBMS 등)는 입력 문장에 해당 기술명이나 연관 내용이 명확히 포함되어 있을 단어만 문장 끝에 넣는다.
       그렇지 않으면 넣지 않는다.
    4. '소프트웨어 솔루션' 또는 '플랫폼 솔루션' 등 중복/유사 표현은 절대 사용하지 않는다.
    5. 본 제품명이나 제조사는 반드시 제외한다. 단, 해당 제품과 연동하는 쿠버네티스, AWS 등 연동 제품명은 작성 가능하다.
    6. 요약 대상 메뉴얼 텍스트에 포함되지 않은 임의의 기술명, 기능, 연관 단어를 추가하지 않는다.
    7. 오직 매뉴얼에 작성된 내용에만 기반하여 한 문장으로 요약문만 작성하고, 요약문 외에는 어떠한 문구도 제공 금지.
    아래는 요약 대상 매뉴얼 텍스트야:
    \"\"\"{source_text}\"\"\"
    """

    logger.debug("Gemini/Gemma summary request start")
    try:
        result_text = generate_gemma_text(prompt)
        logger.debug("Gemini/Gemma summary response: %s", result_text)
        return result_text

    except GemmaConfigError as e:
        logger.warning("Gemini/Gemma config error: %s", e)
        return f"❌ {e}"
    except GemmaGenerationError as e:
        logger.warning("Gemini/Gemma generation error: %s", e)
        return "❌ Gemma 응답 생성 중 오류가 발생했습니다."


# 기존 import 경로 호환용. 새 코드에서는 run_gemini_gemma를 직접 사용하는 것을 권장한다.
def run_openai_GPT(query):
    return run_gemini_gemma(query)


def _normalize_text(value):
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def generate_recommended_summaries(source_text, count=5, max_chars=60):
    """입력 내용에 근거한 제품 개요 추천 문장을 JSON으로 생성한다."""
    normalized_source = _normalize_text(source_text)
    if not normalized_source:
        raise GemmaGenerationError("추천 문장을 생성할 입력 내용이 없습니다.")

    prompt = f"""
너는 소프트웨어 제품 개요 작성 전문가다.

아래 입력 내용과 의미가 유사하면서 표현과 강조 기능이 서로 다른 제품 개요 문장을 정확히 {count}개 작성하라.

작성 조건:
1. 각 문장은 공백을 포함해 {max_chars}자 이내로 작성한다.
2. 입력에 실제로 포함된 목적, 기능, 기술만 사용하고 새로운 사실을 만들지 않는다.
3. 제품명과 제조사명은 제외한다.
4. 각 문장은 단독으로 유사 제품 검색에 사용할 수 있는 완결된 한 문장이어야 한다.
5. 서로 동일하거나 거의 같은 문장을 반복하지 않는다.

입력 내용:
\"\"\"{normalized_source}\"\"\"

반환 형식:
- 설명이나 마크다운 없이 JSON 객체만 반환한다.
- recommendations 배열에 문자열 {count}개를 넣는다.

예:
{{"recommendations": ["제품 개요 문장 1", "제품 개요 문장 2"]}}
"""

    logger.debug("Gemini/Gemma recommendation request start")
    result_text = generate_gemma_text(prompt)
    parsed = extract_json_object(result_text)
    raw_items = parsed.get("recommendations") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        raise GemmaGenerationError("추천 문장 응답 JSON을 해석할 수 없습니다.")

    recommendations = []
    seen = set()
    for item in raw_items:
        text = _normalize_text(item)[:max_chars].strip()
        if not text or text in seen or text == normalized_source:
            continue
        recommendations.append(text)
        seen.add(text)
        if len(recommendations) >= count:
            break

    if len(recommendations) != count:
        raise GemmaGenerationError(
            f"{max_chars}자 이내 추천 문장 {count}개를 생성하지 못했습니다."
        )
    return recommendations


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

    logger.debug("Gemini/Gemma rerank request start")
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


def rerank_multiple_similar_candidates(query_texts, candidates):
    """공통 후보를 문장별로 평가하고 평균 LLM 유사도 순으로 반환한다."""
    normalized_queries = [
        _normalize_text(text)
        for text in query_texts
        if _normalize_text(text)
    ]
    candidate_payload = []
    candidate_by_id = {}

    for row in candidates:
        row_id = str(row.get("일련번호", "")).strip()
        description = _normalize_text(row.get("제품설명"))
        if not row_id or not description:
            continue
        candidate_by_id[row_id] = row
        candidate_payload.append({"id": row_id, "text": description})

    if not normalized_queries or not candidate_payload:
        return []

    prompt = f"""
너는 소프트웨어 제품 유사도 재평가 전문가다.

선택 문장 각각과 모든 후보 제품 설명을 비교하여 실제 목적, 핵심 기능, 기술 영역의 유사도를 평가하라.

평가 기준:
- 핵심 기능과 사용 목적이 직접 일치하면 높게 평가한다.
- 같은 단어가 있어도 목적이 다르면 낮게 평가한다.
- API, 플랫폼, 관리, 데이터, 솔루션, 시스템 같은 일반 단어만 겹치면 낮게 평가한다.
- 단순 연동, 부가 기능, 저장/관리 기능만 유사하면 낮게 평가한다.

선택 문장 JSON:
{json.dumps(normalized_queries, ensure_ascii=False)}

후보 목록 JSON:
{json.dumps(candidate_payload, ensure_ascii=False)}

반환 형식:
- 설명이나 마크다운 없이 JSON 객체만 반환한다.
- 모든 후보를 results 배열에 정확히 한 번씩 포함한다.
- scores는 선택 문장 순서와 같은 0~100 정수 배열이다.
- 각 항목은 id와 scores만 포함한다.

예:
{{
  "results": [
    {{"id": "123", "scores": [95, 87]}}
  ]
}}
"""

    logger.debug("Gemini/Gemma multiple rerank request start")
    rerank_model = os.environ.get("GEMINI_RERANK_MODEL") or DEFAULT_RERANK_MODEL
    result_text = generate_gemma_text(prompt, model=rerank_model)
    parsed = extract_json_object(result_text)
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list):
        raise GemmaGenerationError("LLM 다중 유사도 응답 JSON을 해석할 수 없습니다.")

    scores_by_id = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        row_id = str(item.get("id", "")).strip()
        raw_scores = item.get("scores")
        if row_id not in candidate_by_id or not isinstance(raw_scores, list):
            continue
        if len(raw_scores) != len(normalized_queries):
            continue
        try:
            scores = [
                max(0, min(100, int(round(float(score)))))
                for score in raw_scores
            ]
        except (TypeError, ValueError):
            continue
        scores_by_id[row_id] = scores

    if len(scores_by_id) != len(candidate_payload):
        raise GemmaGenerationError("LLM이 일부 후보의 문장별 유사도를 반환하지 않았습니다.")

    reranked = []
    for row_id, row in candidate_by_id.items():
        scores = scores_by_id[row_id]
        average_score = sum(scores) / len(scores)
        result_row = dict(row)
        result_row.pop("faiss_scores", None)
        result_row["faiss_similarity"] = float(row.get("faiss_similarity") or 0.0)
        result_row["llm_score"] = round(average_score, 2)
        result_row["similarity"] = average_score / 100
        reranked.append(result_row)

    reranked.sort(key=lambda row: row["similarity"], reverse=True)
    return reranked
