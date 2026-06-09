# -*- coding: utf-8 -*-
import logging

from main.utils.gemini_gemma import extract_json_object, generate_gemma_text


logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """너는 SW 제품 분류와 검색 키워드를 추천하는 전문가야.
{INPUT}

위 입력은 시험성적서에서 추출한 제품 설명과 주요 기능이다.
입력 내용에만 근거해서 SW 분류와 검색 키워드 2개를 추천해줘.

규칙:
1. SW는 입력 내용에서 명확히 판단 가능한 간단한 분류명으로 작성한다. 판단하기 어렵다면 빈 문자열로 둔다.
2. keyword1, keyword2는 사용자가 유사 제품을 검색할 때 입력할 만한 핵심 단어로 작성한다.
3. 제품명이나 회사명 자체보다 기능/도메인 중심 단어를 우선한다.
4. 입력에 없는 기술명이나 기능을 추정해서 추가하지 않는다.
5. JSON 이외의 문구는 출력하지 않는다.

반드시 아래 JSON 객체 하나만 출력해줘.
{{
  "SW": "",
  "keyword1": "",
  "keyword2": ""
}}
"""


def classify_sw_and_keywords(input_text: str):
    logger.debug("Gemini/Gemma prdinfo request start")
    prompt = _PROMPT_TEMPLATE.replace("{INPUT}", input_text)
    try:
        content = generate_gemma_text(prompt)
        logger.debug("Gemini/Gemma prdinfo response: %s", content)
    except Exception as e:
        logger.warning("Gemma prdinfo call failed: %s", e)
        return None

    data = extract_json_object(content or "")
    if not isinstance(data, dict):
        return None
    return {
        "SW": data.get("SW", "").strip(),
        "keyword1": data.get("keyword1", "").strip(),
        "keyword2": data.get("keyword2", "").strip(),
    }
