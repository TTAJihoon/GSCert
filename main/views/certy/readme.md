# prdinfo(제품정보요청) 모듈 구성 요약

이 프로젝트는 **Luckysheet**를 이용해 웹페이지에서 업로드한 **Word(.docx), Excel(.xlsx)** 파일의 내용을 파싱하고,  
**엑셀 템플릿(prdinfo.xlsx)**에 매핑한 뒤 **엑셀처럼 표시/편집**하고 **다운로드**까지 이어지는 흐름을 제공합니다.

---

## 1) 파일별 역할 요약

### `prdinfo_URL.py` — 원본 템플릿(prdinfo.xlsx) 내려주기
- 서버에 있는 **원본 엑셀 템플릿**(`main/data/prdinfo.xlsx`)을 그대로 `FileResponse`로 반환합니다.
- 프론트(Luckysheet)가 “빈 양식”을 띄울 때 이 엔드포인트를 호출하는 용도입니다.

### `prdinfo_generate.py` — 업로드(합의서/성적서/결함엑셀) 파싱 통합 API
- 사용자가 업로드한 파일(최대 3개)을 파일명 규칙으로 분류합니다.
  - `합의서*.docx` → 1번 프로세스(합의서)
  - `성적서*.docx` → 2번 프로세스(성적서/결과서)
  - `결함(리포트)*.xlsx` → 3번 프로세스(결함엑셀)
- 각 파서로 분석한 결과 dict를 만들고,
- `build_fill_map()`에 넣어 **시트명 → 셀주소 → 값** 형태의 `fillMap`을 만들어 JSON으로 반환합니다.
- 프론트는 이 `fillMap`으로 Luckysheet 셀을 자동으로 채웁니다.

### `prdinfo_parse_agreement.py` — (1번) 시험합의서(docx)에서 “기본정보” 추출
- `.docx`를 zip으로 열고 `word/document.xml`을 `lxml`로 읽어 표(table) 셀 텍스트를 훑습니다.
- 라벨(예: “대표자”, “사업자등록번호”) 기준으로 **오른쪽 셀 값**을 추출합니다.
- 담당자/대표자 E-mail이 섞이는 문제를 줄이기 위한 스캐너 로직이 포함되어 있습니다.

### `prdinfo_parse_report.py` — (2번) 시험성적서/결과서(docx)에서 개요/기간/기능/WD 합 추출 + GPT 키워드
- docx(문단/표)를 줄 단위로 직렬화해서 다음을 추출합니다.
  1) “7. 시험방법” 전까지 날짜가 포함된 라인 → `시험기간[]`
  2) 제품 설명 구간 → `개요 및 특성(설명)`
  3) 주요 기능 목록 구간 → `개요 및 특성(주요 기능)[]`
  4) 표에서 ‘소요일수’ 숫자 합산 → `소요일수 합계`
- (설명+기능)을 합쳐 `prdinfo_GPT.classify_sw_and_keywords()`를 호출해 **SW 분류/키워드**를 보강합니다.

### `prdinfo_GPT.py` — (보조) OpenAI로 키워드 2개 추천
- OpenAI `responses.create()`로 텍스트를 보내고,
- 응답에서 `{ ... }` JSON 블록만 파싱해 `keyword1/keyword2`를 반환합니다.
- `prdinfo_parse_report.py`에서 호출됩니다.

### `prdinfo_parse_defects.py` — (3번) 결함리포트(xlsx)에서 결함 수 집계 추출
- 업로드된 xlsx에서 “시험분석자료” 시트를 찾고,
- D열 키워드(“품질특성별 결함내역”, “결함정도별 결함내역”) 위치를 기준으로
- 해당 구간의 E열 숫자를 읽어:
  - `적합성~요구사항(9개)` + `High/Medium/Low/합계(4개)`
  값을 `수정전` 항목에 채웁니다.
- 파일명에 `v3` 같은 표기가 있으면 결함차수도 추정합니다.

### `prdinfo_fillmap.py` — 파싱 결과 3개(obj1/2/3)를 “템플릿 셀 주소”에 매핑
- `obj1(합의서)` + `obj2(성적서/결과서)` 내용을 시트 **“제품 정보 요청”**의 특정 셀(D5, B5, B7 …)로 매핑합니다.
- `obj3(결함)`을 시트 **“결함정보”**의 B4~O4로 매핑합니다.
- “한 셀에 2줄” 같은 값은 `\n`으로 합쳐서 넣습니다.

### `prdinfo_download.py` — Luckysheet 편집값으로 “채운 엑셀” 생성/다운로드
- 프론트가 Luckysheet에서 범위 값을 모아 JSON으로 POST 하면,
- 서버가 **원본 템플릿(prdinfo.xlsx)**을 메모리에 로드해 해당 셀/행에 값을 써넣고,
- 줄바꿈 표시를 위해 `wrap_text=True`도 적용한 뒤,
- 파일을 서버에 저장하지 않고 **즉시 다운로드 응답**으로 반환합니다.
- 템플릿 바이트를 전역 캐시해 디스크 I/O를 줄이는 최적화가 포함되어 있습니다.

### `prdinfo_db.py` — 시험번호로 reference.db에서 인증/제품/WD 조회
- 쿼리스트링 `cert_no`를 받아 SQLite(`main/data/reference.db`)의 `sw_data` 테이블에서
  `시험번호=?`로 조회하여 `인증번호, 제품, 총WD`를 JSON으로 반환합니다.
- 보통 “시험번호 입력 → 제품 정보 자동 채움” UI에서 호출합니다.

---

## 2) 파일 호출 관계(의존/호출 그래프)

### 백엔드(파이썬) 내부 호출
- `prdinfo_generate.py`
  - → `prdinfo_parse_agreement.extract_process1_docx_basic()`
  - → `prdinfo_parse_report.extract_process2_docx_overview()`
  - → `prdinfo_parse_defects.extract_process3_xlsx_defects()`
  - → `prdinfo_fillmap.build_fill_map()`
- `prdinfo_parse_report.py`
  - → `prdinfo_GPT.classify_sw_and_keywords()`
- `prdinfo_download.py`, `prdinfo_URL.py`, `prdinfo_db.py`
  - 다른 파이썬 모듈을 직접 호출하지 않는 **독립 엔드포인트** 성격

---

## 3) Luckysheet 기준 전체 동작 흐름(권장 시나리오)

1. **템플릿 로드**
   - 프론트 → `prdinfo_URL` 호출 → 원본 `prdinfo.xlsx` 수신 → Luckysheet에 표시

2. **파일 업로드 & 자동 파싱**
   - 프론트 → `prdinfo_generate`로 docx/xlsx 업로드
   - 서버 → (합의서/성적서/결함) 파싱 → `fillMap` JSON 반환

3. **Luckysheet 셀 자동 채움**
   - 프론트 → `fillMap`의 (시트명, 셀주소)대로 Luckysheet 셀 값 세팅

4. **사용자 최종 수정(웹에서 엑셀처럼 편집)**

5. **다운로드**
   - 프론트 → Luckysheet 범위값을 JSON으로 수집 → `prdinfo_download`에 POST
   - 서버 → 템플릿에 값 반영한 새 xlsx를 즉시 응답(다운로드)

(선택) **시험번호 자동조회**
- 프론트 → `prdinfo_db?cert_no=...` 호출 → 제품명/인증번호/WD 등을 UI에 채움

---

## 4) 다음에 더 정확히 “프론트 호출 순서”를 정리하려면
`static/scripts/certy/prdinfo_*.js` (Luckysheet 초기화/업로드/셀채움/다운로드) 코드까지 함께 보면  
실제 호출 URL/파라미터/이벤트 흐름을 1:1로 정리할 수 있습니다.
