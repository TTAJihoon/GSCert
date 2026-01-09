# testing 모듈(History / Security / Similar) 코드 구성 요약

이 문서는 `views/testing/` 계열의 코드들을 대상으로,
각 파일의 역할과 **서로 어떤 파일(함수)이 어떤 파일을 호출하는지**를 정리합니다.

- **history**: 시험 이력 조회
- **security**: 보안성 결함리포트(Invicti HTML 파싱 + GPT 권고)
- **similar**: 유사 제품 조회(문서 요약 + 벡터 검색 + 결과 반환)

---

## 0) 전체 아키텍처 개요

### History(시험 이력 조회)
- DB(`main/data/reference.db`)의 `sw_data` 테이블을 조건 검색
- 결과를 `testing/history.html` 템플릿에 렌더링

### Security(보안성 결함리포트 작성)
- Invicti HTML 리포트 업로드 → 서버에서 취약점 섹션을 파싱 → 표 형태(JSON)로 반환
- 개별 결함에 대해 GPT “수정 권고”를 요청할 수 있는 API 제공(프롬프트 기반)

### Similar(유사 제품 조회)
- PDF/DOCX/PPTX 업로드 또는 텍스트 입력 → 텍스트 추출/전처리
- GPT로 “한 문장 제품 요약” 생성 → FAISS 벡터 검색으로 유사 제품 상위 k개 조회
- 요약 + 유사 결과 리스트 + 유사도 배열을 JSON으로 반환

---

## 1) History: 시험 이력 조회

### 1.1 `history.py`
**역할**
- `history(request)`:
  - POST 입력값(인증번호/시험번호/회사/제품/기간/코멘트)을 받아 DB 검색 함수 `GS_history()`를 호출
  - 결과 rows를 key 정리(공백/개행/슬래시 치환, `Unnamed` 제거, `None` → '-') 후
  - `testing/history.html`에 `response_tables`로 전달하여 렌더링
- `GS_history(...)`:
  - `sqlite3`로 `main/data/reference.db` 연결
  - `sw_data`에 대해 LIKE 조건(인증번호/시험번호/회사/제품/제품설명) + 기간 조건(시작일자/종료일자) 동적 구성
  - 결과를 list[dict]로 반환

**백엔드 의존**
- DB: `main/data/reference.db` / 테이블: `sw_data`

**호출 관계**
- `history()` → `GS_history()` (동일 파일 내부 호출)

---

## 2) Security: 보안성 결함리포트(Invicti) 파싱 + GPT 권고

### 2.1 `security.py`
**역할**
- `invicti_parse_view(request)`:
  - 여러 개의 `.html/.htm` 리포트 파일 업로드를 받아 순회 처리
  - 파일 형식/크기(10MB) 검증
  - 각 파일의 HTML을 `extract_vulnerability_sections()`로 파싱
  - 첫 번째 파일에서 CSS를 확보하고, 모든 파일에서 rows를 합쳐 JSON으로 반환:
    - `{ "css": "...", "rows": [...] }`

**호출 관계**
- `security.py` → `security_extractHTML.extract_vulnerability_sections()`

---

### 2.2 `security_extractHTML.py`
**역할**
- Invicti HTML 구조에서 **Critical/High/Medium** 취약점 블록을 찾아 아래 데이터를 추출/가공합니다.

1) **매핑 템플릿 로드**
- `main/data/security.xlsx`의 `Sheet1`을 `pandas`로 로드하여,
  - Invicti 항목명 ↔ TTA 결함리포트 템플릿(요약/결함내용) 매핑에 사용합니다.
- fuzzy matching(`fuzzywuzzy.fuzz.token_set_ratio`)으로 제목 유사도를 계산해 가장 잘 맞는 템플릿을 선택합니다.

2) **Invicti 취약점 상세(JSON) 추출**
- 취약점 상세 영역(`vuln-detail`)에서:
  - 표(table) 구조를 컬럼/로우 JSON으로 변환
  - 코드 블록(pre.cprompt) 추출
  - h4 + ul/a 형태의 key-value/link 추출
  - Request/Response 영역의 pre/code 텍스트 추출
- 결과를 `vuln_detail_json`로 row에 포함합니다.

3) **템플릿 변수 치환**
- 특정 항목(번호)에 대해:
  - URL 목록, 약한 암호 목록, 최신버전/확인된 버전 등
  - 취약점 블록에서 변수들을 추출해 `{o}`, `{url}`, `{weak}`, `{v1}`, `{v2}` 같은 placeholder를 템플릿에 치환합니다.

4) **GPT 권고 프롬프트 생성**
- `vuln_detail_json`을 JSON 문자열로 만들어
  - “구체적인 해결 방안을 한글로 제시”하도록 하는 `gpt_prompt`를 생성합니다.
- 실제 GPT 호출은 **이 파일에서 하지 않고**(프롬프트만 생성),
  - 프론트가 이 프롬프트를 `security_GPT.py` API로 보내는 구조입니다.

5) **안전한 HTML 스니펫 반환**
- Invicti 분석 화면(HTML)을 프론트에서 보여주기 위해,
  - `bleach` + `CSSSanitizer`로 허용 태그/속성/CSS만 남기고 sanitize한 `invicti_analysis`를 row에 담습니다.

**출력 row 주요 필드**
- `defect_summary`, `defect_description`, `defect_level(H/M)`, `invicti_report`, `invicti_analysis`, `vuln_detail_json`, `gpt_prompt` 등

**호출 관계**
- (entry) `extract_vulnerability_sections(html_content)` 내부에서 다수의 헬퍼 함수 호출
- 외부에서는 `security.py`가 이 함수를 호출

---

### 2.3 `security_GPT.py`
**역할**
- `get_gpt_recommendation_view(request)`:
  - 프론트에서 JSON으로 받은 `prompt`를 OpenAI로 전달
  - 모델명은 `"gpt-5-nano"`로 고정
  - 응답 텍스트를 `{ "response": "..." }`로 반환
  - 모델명이 없거나(키 누락), 모델이 존재하지 않는다는 에러 메시지에 대해 안내 문구를 보강

**호출 관계**
- 프론트(보안성 페이지) → `security_GPT.get_gpt_recommendation_view()`
- 이 API는 `security_extractHTML.py`가 만든 `gpt_prompt`를 전달받아 실행하는 용도

> ⚠️ 참고: 이 파일은 OpenAI `chat.completions.create()`를 사용합니다.  
> 프로젝트의 다른 코드(prdinfo)는 `responses.create()`를 사용하므로, API 방식이 서로 다릅니다.

---

## 3) Similar: 유사 제품 조회(요약 + FAISS 검색)

### 3.1 `similar_summary.py`
**역할**
- 파일 업로드(PDF/DOCX/PPTX) 또는 수동 텍스트 입력을 받아 텍스트를 확보
- 전처리(`preprocess_text`) 후 문장 분리
- `run_openai_GPT(sentences)`로 “한 문장 제품 개요(100자 미만)” 생성
- `compare_from_index(summary_text)`로 벡터 검색 → 유사 제품 목록 + 유사도 점수 반환
- 최종 응답:
  - `{ summary, response: compare_result, similarities: similarity_list }`

**텍스트 추출 지원**
- PDF: PyMuPDF(fitz)
- DOCX: zip + lxml(objectify)로 문단/표 텍스트 추출(세로 병합 continue 셀 skip)
- PPTX: python-pptx로 슬라이드 텍스트 추출

**호출 관계**
- `similar_summary.py` → `similar_GPT.run_openai_GPT()`
- `similar_summary.py` → `similar_compare.compare_from_index()`

---

### 3.2 `similar_GPT.py`
**역할**
- `run_openai_GPT(query)`:
  - 입력(매뉴얼 텍스트)을 기반으로 “제품 설명 1문장(100자 미만)”을 생성하는 프롬프트 구성
  - OpenAI `chat.completions.create()` 호출 (모델 `"gpt-5-nano"`)
  - 결과 텍스트(문장)만 반환

**호출 관계**
- `similar_summary.py`에서 호출됨(요약 생성 단계)

---

### 3.3 `similar_compare.py`
**역할**
- `compare_from_index(text, k=30)`:
  1) FAISS 인덱스 로드: `main/data/faiss_bge_m3_ko.idmap.index`
  2) 문장 임베딩: `SentenceTransformer("upskyy/bge-m3-korean")`
  3) 검색: inner product(IP) 기반으로 top-k 조회 (라벨=DB 일련번호)
  4) DB 조회: `select_data_from_db(indices)`로 `reference.db`의 `sw_data`에서 `일련번호 IN (...)`
  5) 각 row에 `similarity` 필드 부여
  6) **주의: 최종 정렬을 유사도 순이 아니라 `일련번호 내림차순`으로 다시 정렬**
     - 즉, 검색 결과 순서(유사도 랭킹)가 화면 표시에서 깨질 수 있습니다.

**호출 관계**
- `similar_summary.py`에서 호출됨(유사 제품 검색 단계)

---

## 4) 호출 그래프(요약)

### History
- `history.py: history()` → `history.py: GS_history()`

### Security
- `security.py: invicti_parse_view()` → `security_extractHTML.py: extract_vulnerability_sections()`
- (프론트) → `security_GPT.py: get_gpt_recommendation_view()`  
  - 전달 프롬프트는 `security_extractHTML.py`가 row별로 생성한 `gpt_prompt`

### Similar
- `similar_summary.py: summarize_document()`  
  → `similar_GPT.py: run_openai_GPT()`  
  → `similar_compare.py: compare_from_index()`  
  → (내부) `select_data_from_db()`

---

## 5) 운영/품질 관점 체크 포인트(짧게)

- **OpenAI 모델명 `"gpt-5-nano"`**
  - 실제 계정/플랜/모델 제공 여부에 따라 에러가 날 수 있어 예외 처리가 중요합니다.
- **similar_compare.py 정렬 로직**
  - 유사도 순으로 보여주려면 `일련번호 내림차순 정렬`은 제거하거나 옵션으로 분리하는 게 안전합니다.
- **security_extractHTML.py의 sanitize**
  - 허용 태그/속성이 꽤 넓어 프론트 표시에는 유리하지만, 추후 XSS/스타일 깨짐 이슈가 있으면 허용 목록을 다시 점검하는 포인트입니다.
