# -*- coding: utf-8 -*-
import os, json, re
from openai import OpenAI

# 환경변수 OPENAI_API_KEY 필요
_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_PROMPT_TEMPLATE = """너는 SW 프로그램을 분류하고 핵심 키워드를 추천하는 전문가야.
{INPUT}
위에서 입력 받은 값에 대해 핵심 키워드를 작성해줘.
누군가가 해당 제품을 검색하고 싶을 때, 입력할만한 단어 2개를 핵심 키워드로 작성해줘.

결과 출력은 json 형태로 출력해줘. json 이외의 어떠한 말도 작성하지 말아줘.
{
 keyword1: (첫번째 핵심 키워드)
 keyword2: (두번째 핵심 키워드)
}
"""

def _extract_json(s: str):
    # 가장 바깥 { ... } 블록만 추출
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # JSON에 따옴표 누락 등 경미한 오류 시 재시도 (쌍따옴표 강제 등은 생략)
        return None

def classify_sw_and_keywords(input_text: str):
    print("[STEP 1] GPT 요청 시작")
    prompt = _PROMPT_TEMPLATE.replace("{INPUT}", input_text)
    resp = _client.responses.create(
        model="gpt-5-nano",
        input=prompt
    )
    # responses API: 첫 메시지 텍스트 추출
    try:
        content = resp.output_text
        print(content)
    except Exception:
        # 구버전 SDK 호환
        try:
            content = resp.choices[0].message["content"]
        except Exception as e:
            print("GPT 에러 발생" + e)
            content = ""

    data = _extract_json(content or "")
    if not isinstance(data, dict):
        return None
    return {
        "SW": data.get("SW", "").strip(),
        "keyword1": data.get("keyword1", "").strip(),
        "keyword2": data.get("keyword2", "").strip(),
    }
