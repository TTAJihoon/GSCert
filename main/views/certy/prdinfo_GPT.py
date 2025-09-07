# -*- coding: utf-8 -*-
import os, json, re
from openai import OpenAI

# 환경변수 OPENAI_API_KEY 필요
_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_PROMPT_TEMPLATE = """너는 SW 프로그램을 분류하고 핵심 키워드를 추천하는 전문가야.
{INPUT}
위에서 입력 받은 값에 대해 SW 분류 항목과 핵심 키워드를 작성해줘.
첫번째로 SW 분류 항목은 아래 항목을 참고해서 작성해줘.
'-'으로 작성된 값은 대분류이고 '--'로 작성된 값은 소분류야.
대분류를 먼저 선택하고 해당 대분류에 속해있는 소분류를 선택해서 SW 분류 항목을 작성해줘.
(예, 유틸리티 SW-압축)
-유틸리티 SW
--압축
--웹브라우저
--원격제어
--메신저 
--리포팅 
--언어 번역 
--데이터영구삭제 
--데이터백업/복구 
--화상회의 
--문서회의 
--FTP 
--PDF변환 
--형상관리 
--이미지뷰어 
--가상CD드라이브 
--메타데이터 관리 
--기타 
-보안용 SW
--PC보안 
--DB보안 
--서버보안 
--웹보안 
--키보드보안 
--침입차단(방화벽) 
--침입탐지(IDS) 
--스팸및악성코드차단 
--바이러스백신 
--인증관리(PKI,SSO) 
--디지털콘텐츠보안 
--통합보안관리(ESM) 
--기타 
-기업용
--그룹웨어(Groupware)
--비즈니스관리(BPM)
--전사적자원관리(ERP)
--고객관계관리(CRM)
--공급망관리(SCM)
--기업포털(EIP)
--지식관리(KMS)
--경영정보관리(MIS)
--인적자원관리(HR)
--프로젝트관리(PMS)
--회계관리
--고객상담지원
--자동차운전학원관리
--기타
-디지털콘텐츠 SW
--웹페이지저작
--멀티미디어저작
--디지털콘텐츠관리(CMS)
--디지털음성처리
--전자출판
--그래픽편집
--CAD/CAM
--기타
-임베디드 SW
--RFID
--Zigbee
--공정제어
--의료장비용
--방송장비용
--임베디드용
--교통및주차관리
--기타
-시스템관리 SW
--시스템 관리(SMS)
--네트워크 관리(NMS)
--스토리지 관리
--성능 측정 및 관리
--패치 관리(PMS)
--통합 관리(EMS)
--PC 관리
--홈네트워크
--텔레매틱스
--감시장비제어
--기타
-미들웨어 SW
--WAS
--검색엔진
--이동단말기
--전사적애플리케이션통합(EAI)
--기타
-바이오매트릭스 SW
--지문 인식
--음성 인식
--홍체 인식
--얼굴 인식
--기타
-사무용 SW
--프리젠테이션
--워드프로세서
--스프레드쉬트
--오피스
--문서 뷰어
--기타
-운영체제 SW
--윈도우즈 운영체제
--유닉스 운영체제
--리눅스 운영체제
--임베디드  운영체제
--기타
-웹서비스용 SW
--웹메일
--웹하드
--웹포털
--웹서버
--단문자발송(SMS)
--기타
-게임용 SW
--모바일 게임
--온라인 게임
--아케이드 게임
--비디오 게임
--PC패키지 게임
--기타
-데이터베이스 SW
--DBMS
--DB관리
--DB리포팅
--기타
-프로그램개발 관련 SW
--프로그램개발지원
--시험도구
--소스코드분석
--모델링도구
--기타
-GIS SW
--상하수도시설물관리
--도로시설물관리
--도로및상하수도시설물관리
--기타
-주문형(SI) SW
--주문형(SI)
-교육용 SW
--온라인(e-learning)교수학습
--오프라인교수학습
--교수학습지원
--기타

그리고 두번째로 핵심 키워드는 누군가가 해당 제품을 검색하고 싶을 때, 입력할만한 단어 2개를 작성해줘.

결과 출력은 json 형태로 출력해줘. json 이외의 어떠한 말도 작성하지 말아줘.
{
 SW: (SW 분류 항목 값)
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
