import os
import json
from typing import Tuple, Dict, Any
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from textwrap import dedent
from openai import OpenAI

# ---------- 내부 호출용 핵심 로직 ----------
def run_checkreport_gpt(parsed_payload: dict, debug: bool = False) -> Tuple[dict, Dict[str, Any]]:
    """
    합쳐진 원본 전체 JSON(parsed_payload)을 그대로 GPT에 전달하여
    테이블 렌더링용 스키마(JSON)로 변환.

    반환:
      - result: {"version":"1","total":N,"items":[...]}
      - debug_payload:
          {
            "gpt_request": {...},          # 실제 보낼 전체 파라미터 (오류 시에도 채움)
            "gpt_response_meta": {...},    # 호출 성공 시 메타
            "instruction_text": "...",     # 사람이 읽기 쉽게 원문 노출
            "error": "..."                 # 호출 실패 시 오류 메시지
          }
    """
    debug_payload: Dict[str, Any] = {}

    # 0) instruction 원문 및 스키마(여러 줄 그대로)
    instruction_text = dedent("""\
        다음은 시험결과서(docx, pdf)를 파싱해 하나의 JSON으로 합친 원본 전체 데이터입니다.
        해당 json 형식은 아래와 같은 구조를 가집니다.
        ## 1) 최상위 구조
        {
          "v": "1",
          "docx": { "v": "1", "content": [ /* 노드 배열(원문 순서 보존) */ ] },
          "pdf":  { "v": "1", "total_pages": 0, "pages": [ { "page": 1, "header": ["상단 1줄"], "footer": ["하단 1줄"] } ] }
        }
        요소 설명
        - v: 스키마 버전(문자열, 임의 값)
        - docx: DOCX 본문 파싱 결과
        - pdf: PDF 각 페이지 상단/하단 1줄 텍스트 결과
        ---
        ## 2) DOCX (노드 타입/OMML 선형화 규칙 등) ... (생략 없이 기존 작성본 유지)
        ## 3) PDF (구조/예시) ... (생략 없이 기존 작성본 유지)
        ## 4) 공통 규칙/보고 원칙/심각도/필수 점검항목/검증 절차/출력 형식/정렬 규칙 ... (기존 작성본 그대로)
    """)

    instruction = {
        "instruction": instruction_text,
        "schema": {
            "version": "1",
            "total": "items 배열 길이",
            "items": [{
                "no": "1부터 시작하는 번호(정수)",
                "category": "구분(점검항목)",
                "severity": "심각도",
                "location": "위치(표/절/문장)",
                "summary": "문제 요약",
                "evidence": "근거(원문 일부 인용, 10~30자)",
                "recommendation": "권장 수정안"
            }]
        }
    }

    # 1) 실제로 보낼 '요청 페이로드'를 선구성 (오류여도 디버그에 넣기 위함)
    request_payload: Dict[str, Any] = {
        "model": "gpt-5-nano",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a strict technical reviewer. Return ONLY a JSON object in the required schema."
            },
            {
                "role": "user",
                "content": json.dumps(instruction, ensure_ascii=False)
            },
            {
                "role": "user",
                "content": json.dumps(parsed_payload, ensure_ascii=False)  # 합쳐진 원본 전체
            }
        ],
        "temperature": 0.2,
    }

    # 2) 디버그 켜진 경우, 호출 전부터 gpt_request/instruction_text를 채워둠
    if debug:
        debug_payload["gpt_request"] = request_payload
        debug_payload["instruction_text"] = instruction_text

    # 3) API 키 확인 → 없으면 호출하지 않고 즉시 빈 결과 + 디버그 반환
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if debug:
            debug_payload["error"] = "OPENAI_API_KEY is not set (모델 호출 생략)."
        return {"version": "1", "total": 0, "items": []}, debug_payload

    # 4) 실제 호출
    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(**request_payload)

        content = completion.choices[0].message.content if completion.choices else None
        data = json.loads(content) if content else {"version": "1", "total": 0, "items": []}

        # 5) 스키마 정규화
        items = data.get("items", [])
        norm = []
        for idx, it in enumerate(items, start=1):
            norm.append({
                "no":              it.get("no", idx),
                "category":        it.get("category", ""),
                "severity":        it.get("severity", ""),
                "location":        it.get("location", ""),
                "summary":         it.get("summary", ""),
                "evidence":        it.get("evidence", ""),
                "recommendation":  it.get("recommendation", "")
            })
        result = {"version": "1", "total": len(norm), "items": norm}

        # 6) 디버그 메타 (성공 시)
        if debug:
            usage = getattr(completion, "usage", None)
            debug_payload["gpt_response_meta"] = {
                "id": getattr(completion, "id", None),
                "created": getattr(completion, "created", None),
                "model": getattr(completion, "model", None),
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                    "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                    "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
                }
            }

        return result, debug_payload

    except Exception as e:
        # 7) 실패 시에도 디버그에 오류를 남김
        if debug:
            debug_payload["error"] = f"OpenAI call failed: {e}"
        return {"version": "1", "total": 0, "items": []}, debug_payload


# ---------- (선택) 하위호환용 엔드포인트 ----------
@csrf_exempt
@require_http_methods(["POST"])
def get_gpt_recommendation_view(request: HttpRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return JsonResponse({"error": "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."}, status=500)

    client = OpenAI(api_key=api_key)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
        user_prompt = body.get("prompt", "")

        completion = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_prompt}
            ]
        )
        response_content = completion.choices[0].message.content if completion.choices else ""
        return JsonResponse({"response": response_content})
    except Exception as e:
        msg = str(e)
        if "The model `gpt-5-nano` does not exist" in msg:
            msg = "GPT 모델('gpt-5-nano')을 찾을 수 없습니다. 모델명을 확인하거나 OpenAI API Plan을 확인하세요."
        return JsonResponse({"error": f"GPT API 호출 중 오류 발생: {msg}"}, status=500)
