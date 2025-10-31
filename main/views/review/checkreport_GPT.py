import os
import json
from typing import Tuple, Dict, Any
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from textwrap import dedent
from openai import OpenAI

PARSED_START = "<<PARSED_PAYLOAD_JSON_START>>"
PARSED_END   = "<<PARSED_PAYLOAD_JSON_END>>"

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
        <<PARSED_PAYLOAD_JSON_START>> ~ <<PARSED_PAYLOAD_JSON_END>> 사이에 제공되는 json 값(이하 '원본')은 시험결과서 파일(.docx)를 파싱해 하나의 JSON으로 합친 데이터입니다.
        아래 구조를 참고하여 원본을 하나의 word 문서로 만들어 '판단 지침'에 따라 결과를 제공해줘.

        #### 원본 구조 설명 ####
        ## 1) 최상위 구조
        {
          "v": "1",
          "docx": {
            "v": "1",
            "content": [ /* 노드 배열(원문 순서 보존) */ ]
          },
          "pdf": {
            "v": "1",
            "total_pages": 0,
            "pages": [
              { "page": 1, "header": ["상단 1줄"], "footer": ["하단 1줄"] }
            ]
          }
        }
        요소 설명
        - v: 스키마 버전(문자열, 임의 값)
        - docx: DOCX 본문 파싱 결과
        - pdf: PDF 각 페이지 상단/하단 1줄 텍스트 결과
        ---
        ## 2) DOCX
        ### 2.1 content 노드 타입
        1) 문장 노드
        { "sen": "문단/자유 텍스트(OMML 수식 선형 포함)" }
        2) 라벨(섹션) 노드
        { "label": "제목/번호/첨부", "content": [ /* 하위 노드들 */ ] }
        - 라벨 패턴 예: 숫자 섹션(^\\d+(\\.\\d+)*\\s+), 첨부(^<\\s*첨부\\s*\\d+\\s*>)
        3) 표 노드
        {
          "table": [
            [row, col, row_span, col_span, "셀 텍스트"],
            ...
          ]
        }
        - 좌표 1-based
        - 병합 정보 유지(루트 셀만 기록)
        - "셀 텍스트"는 여러 문단을 \\n 로 연결
        - 표 내부 수식 역시 선형화된 텍스트로 포함
        ### 2.2 목차(TOC)
        - "목 차" 구간: 전부 sen만 생성(라벨/표 없음)
        ### 2.3 OMML 수식 선형화 규칙(문장/표 텍스트에 포함)
        - 분수: (분자)/(분모)
        - 아랫/윗첨자: x_{i}, x^{2}, x_{i}^{n}
        - 시그마/파이: ∑_{하한}^{상한} (...), 상·하한이 비어있으면 생략(예: ∑ (...))
        - 예시(기대 표현):
          X(%) = ∑_{i=1}^{n} (A_{i}+B_{i})/(n)
          Y(%) = ∑_{i=1}^{n} (C_{i}-(D_{i}+E_{i}+F_{i}))/(C_{i})*(1)/(n)*(1)/(1024)*100
        ---
        ## 3) PDF
        구조
        "pdf": {
          "v": "1",
          "total_pages": 15,
          "pages": [
            { "page": 1, "header": ["상단 1줄"], "footer": ["하단 1줄"] },
            ...
          ]
        }
        설명
        - 각 페이지 상단 1줄 → header([] 문자열 배열)
        - 각 페이지 하단 1줄 → footer([] 문자열 배열)
        - 예:
          header: "1/12 소프트웨어시험인증연구소"
          footer: "TPG-1016-5(02)  Copyright 2025 TTA  페이지 : (7)/(총15)"
        ---
        #### 원본 구조 설명 끝 ####

        #### 판단 지침 시작 ####
        Let's think step by step
        ## 역할
        - 당신은 **시험 합의서/시험결과서 기술책임자**입니다.
        - **문서에 존재하는 근거로만** 판단하세요. 문서에 없는 사실·수치·페이지·그림·표는 **추정/생성 금지**. 불확실하면 **“검증불가(근거 없음)”**으로 표기.

        ## 보고 원칙
        - 최우선: **수식/산식 오류 검증 및 재계산**.
        - **대소문자·사소한 띄어쓰기·경미한 문체**는 보고하지 않음(의미·계산 영향 시만 보고).
        - 가능하면 **페이지·위치(표/절/문장)**를 함께 명시(불명확 시 “페이지 불명”).

        ## 심각도 기준
        - 심각: 산식오류로 결과 왜곡, 시험환경/사양 중대 불일치, 안전·규제/버전/의뢰자/번호/기간 불일치
        - 중요: 핵심 기술 불일치, 단위·치수 오류, 결론에 영향 주는 필수 항목 누락
        - 보통: 비논리·불명확 서술, 문맥 유사도 기준 미달
        - 경미: 용어 비표준/표현 개선(의미 동일)

        ## 필수 점검항목
        1. **오타(의미 변형)**
        2. **기술 오류**: 요구사항·사양·결과 상충, 단위/치수/범위 오류
        3. **용어·수치 일관성**
        4. **비논리 문장**(근거 없는 단정 포함)
        5. **수식/산식 오류**: 기호·단위·반올림·%↔소수 혼동·대입값 불일치
        6. **기능리스트 가독성**(CRUDSM 관점)
        7. **<첨부1> 기능리스트 규칙 준수**
        8. **결말 문자열**: 문서 마지막에 “- 끝 -” 또는 “-끝-” 존재
        9. **단어 유사도(5.1 기능적합성 ↔ <첨부1>)**: 유사도 ≤ 30%면 오류(보통)
        10. **시험환경 일치(4.2)**: **<시험환경구성도> ↔ <세부사양> 표** 동일
        11. **목차 페이지 일치(3페이지)**
        12. **제조자 표기**: 4.1 제품구성의 제조자 ↔ 1.1 회사 개요의 회사명 일치
        13. **설치 SW 표기 정확성(<세부사양>)**: 오픈소스/SW명 오류 여부
        14. **제품 구성(4.1)**: 제품명(국문 또는 영문) 포함
        15. **세부사양 표기 명확성**: OS, CPU 표기 오류 없음(예: Intel® Xeon… 형식 일관)
        16. **Copyright 연도 = 6. 시험기간 종료연도(1페이지)**
        17. **목차 번호 오류(3페이지)**
        18. **단어 유사도(1.2 개요 및 특성 ↔ <첨부1>)**: 유사도 ≤ 30%면 오류(보통)
        19. **목적격 조사 누락**(을/를 등)

        ### BT로 시작하는 결과서 추가 점검
        - 3. 시험항목 **측정지표 산식 검증**
        - 3 ↔ 5(시험방법) ↔ 6(시험결과) **항목 일관성**
        - 7. 시험기록 **숫자 계산 검증**

        ## 문맥 유사도(재현 절차)
        (a) 개요·기능리스트·5.1에서 **핵심 키워드 10~30개**씩 추출 →  
        (b) **동등어만 병합**(예: IP 주소=IP Address, 포트 번호=Port Number) →  
        (c) **유사도 = 교집합/합집합 × 100%** →  
        (d) **50% 이하**는 보통으로 보고(겹치는/누락 키워드 예시 인용).

        ## 산식/수치 검증 절차
        1) **기호·변수·단위 정의 확인**  
        2) **차원 일치**(MB/s vs Mb/s, °C vs K, ms vs s 등)  
        3) **대입 재계산** + **반올림 규칙** 확인  
        4) **%↔소수 변환 일관성**  
        5) **상·하한/허용오차** 대비  
        6) 데이터 부족 시 **“검증불가(수치/단위 부재)”**

        ## <첨부1> 기능리스트 규칙(요약)
        - **CRUDSM** 관점 기술(등록/조회/수정/삭제만도 허용).
        - **금지**: 사람 행위 지시 단어(서비스/처리/내역 등), “설정(추가/수정/삭제)” 모호 표현.
        - **개선 가이드**:
          - “현황/기록/로그/이력” → **괄호로 구체화**(예: *이력(시각, 이름, 이벤트 등) 조회*).
          - 형식 명시(예: *데이터 조회 REST API*, *엑셀 파일 다운로드*).
          - **IP 주소**, **포트 번호**, **URL 주소**로 표준화.

        ## 제외·무시(보고하지 않음)
        - 템플릿·꼬리말 혼재, 5~7페이지 전면, 환경 모호 서술 등 **제외 리스트**에 해당하는 항목.
        - **산정식 누락 자체**, Working Day 일반, 설치 SW 열의 HW 혼입 등은 **점검 제외 규정** 준수.

        ## 1.2 개요 및 특성
        - **주요 기능 설명 필수**.
        - **주요 기능 아님**(제외): 사용자 관리/로그인 등 → 실제 핵심 기능으로 대체 권고.

        ## 출력 형식(반드시 준수)
        - **양호 항목은 출력 금지. 오류만 json으로 요약.**
        - **페이지 불명** 시 위치에 “-” 표기.
        - **수정안은 간결·구체·검증가능**하게.
        - **오류가 전혀 없으면**: null 출력.
        - **아래 스키마의 JSON 객체로만 응답하세요.
        {{
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
        }}

        ## 정렬·마감
        - **중요도 순(심각→중요→보통→경미)** 정렬.
        - 문서 끝 **결말 문자열**(“- 끝 -” 또는 “-끝-”) 존재 확인.
        - **추가 가정 금지**, 수치·유사도·페이지는 **지어내지 말 것**. 부족하면 **검증불가**로.
        #### 판단 지침 끝 ####




        
    """).strip()

    # 1) 실제로 보낼 '요청 페이로드'를 선구성 (오류여도 디버그에 넣기 위함)
    request_payload: Dict[str, Any] = {
        "model": "gpt-5",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a strict technical reviewer. Return ONLY a JSON object in the required schema."
            },
            {
                "role": "user",
                "content": json.dumps(instruction_text, ensure_ascii=False)
            },
            {
                "role": "user",
                "content": f"{PARSED_START}\n{json.dumps(parsed_payload, ensure_ascii=False)}\n{PARSED_END}"
            }
        ],
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
            model="gpt-5",
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
