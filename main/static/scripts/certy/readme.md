# prdinfo(제품정보요청) 프론트엔드(JS) 모듈 구성 요약

이 문서는 `static/scripts/certy/`에 있는 **prdinfo 관련 JS 코드들**이 어떤 역할을 하는지,  
그리고 **Django 백엔드(Python 뷰)**와 어떤 엔드포인트로 연동되는지를 정리합니다.

---

## 0) 전체 흐름(요약)

1. **원본 엑셀 템플릿 표시**
   - `prdinfo_Luckysheet.js`가 `/source-excel/`에서 템플릿 XLSX를 받아 **LuckyExcel → LuckyJSON 변환** 후 Luckysheet로 렌더링

2. **파일 업로드 UI(드래그앤드롭/목록/3개 제한)**
   - `prdinfo_upload.js`가 업로드 파일 선택/동기화(DataTransfer) 담당

3. **파싱/자동 채우기(Generate)**
   - `prdinfo_generate.js`가 `/generate_prdinfo/`로 3개 파일을 전송
   - 응답의 `fillMap` + “사전 입력 사항 탭” 값들을 합쳐
   - `prdinfo_fill_cells.js`의 `window.PrdinfoFill.apply(fillMap)` 호출로 Luckysheet에 셀 자동 입력

4. **탭 UI/사전입력 폼 토글/재인증 조회**
   - `prdinfo_tab.js`가 탭 전환, 폼 토글(클라우드/재계약/보안면제 등), `/lookup_cert_info/` 조회 담당

5. **다운로드**
   - **두 방식이 존재**(중복 가능성 주의)
     - (A) 브라우저에서 즉시 export: `prdinfo_Luckysheet.js`가 LuckyExcel로 “Luckysheet → XLSX” 변환하여 다운로드
     - (B) 서버 템플릿 채우기: `prdinfo_download.js`가 Luckysheet 값을 수집해 `/download-filled/`에 POST → 서버가 XLSX 생성 후 응답 다운로드

---

## 1) 백엔드 연동 엔드포인트 맵

| 목적 | 호출 JS | Endpoint | 방식 | 비고 |
|---|---|---|---|---|
| 원본 템플릿 XLSX 로드 | `prdinfo_Luckysheet.js` | `/source-excel/` | GET(blob) | LuckyExcel로 LuckyJSON 변환 후 렌더 |
| 업로드 3개 파싱 + fillMap 생성 | `prdinfo_generate.js` | `/generate_prdinfo/` | POST(FormData) | 응답: `fillMap`, `list1/2/3`, `gsNumber` 등 |
| 재인증 제품 조회 | `prdinfo_tab.js` | `/lookup_cert_info/?cert_no=...` | GET(json) | 응답: `success`, `data(cert_id, product_name, total_wd)` |
| 템플릿에 값 채워 XLSX 다운로드 | `prdinfo_download.js` | `/download-filled/` | POST(json) | 서버가 템플릿 기반으로 새 XLSX 생성 후 응답 |
| (대안) Luckysheet → XLSX 직접 export | `prdinfo_Luckysheet.js` | (없음) | client-side | `LuckyExcel.transformLuckyToExcel()` |

---

## 2) 파일별 역할 요약

### `prdinfo_Luckysheet.js` — “템플릿 불러와 Luckysheet 렌더” + (클라 export) 다운로드
- 페이지 로드 시 `/source-excel/`로 **서버 템플릿 XLSX**를 가져옵니다.
- `LuckyExcel.transformExcelToLucky()`로 XLSX → LuckyJSON 변환 후 `luckysheet.create()`로 렌더합니다.
- `#btn-download` 클릭 시 현재 시트를 모아 `LuckyExcel.transformLuckyToExcel()`로 **바로 XLSX 다운로드**도 수행합니다.
- 파일명은 D5 값을 이용해 안전한 파일명으로 정리합니다.

> ⚠️ 주의: `prdinfo_download.js`도 `#btn-download`에 이벤트를 바인딩합니다.  
> 둘 다 로드되면 “다운로드 버튼 클릭 시 핸들러가 2개 실행”될 수 있어 충돌 위험이 있습니다.

---

### `prdinfo_upload.js` — 파일 업로드 UX(드래그앤드롭, 목록, 3개 제한)
- 드래그앤드롭/클릭 업로드를 지원합니다.
- 최대 3개, 허용 확장자 `pdf/docx/xlsx`, 중복 파일(이름+크기+mtime) 제거
- 내부 배열 `selectedFiles`를 유지하고, `DataTransfer`로 `<input type=file>`의 `files`를 동기화하여
  **서버 전송은 항상 `fileInput.files` 기준**이 되도록 맞춥니다.

---

### `prdinfo_generate.js` — 업로드 3개 검증 → `/generate_prdinfo/` 호출 → fillMap 적용
- 업로드 파일이 **정확히 3개인지** 확인하고, 파일명에 키워드 포함 여부를 검사합니다.
  - 합의서 / 성적서 / 결함리포트(또는 결함)
- fetch로 `/generate_prdinfo/`에 `FormData`를 POST하고, 응답에서 `fillMap`을 받습니다.
- “사전 입력 사항 탭”의 폼 값들을 읽어 `fillMap` 형태로 만든 후 서버 fillMap에 merge합니다.
  - 예: `E5`(SW 분류), `L5`(시험원), `B9/D9`(클라우드 환경), `F9`(SaaS), `I5`(재계약), `G9/H9`(재인증), `J9/L9`(보안성 면제/상세)
- 최종 `fillMap`을 `window.PrdinfoFill.apply()`에 넘겨 Luckysheet에 셀을 채웁니다.
- 완료 후 “결과 탭(resultSheet)”으로 자동 전환합니다.

---

### `prdinfo_fill_cells.js` — `fillMap`을 Luckysheet에 실제로 입력하는 “셀 채우기 엔진”
- `window.PrdinfoFill.apply(fillMap)` 형태로 전역에 노출됩니다.
- `fillMap` 구조:
  - `{ "시트명": { "A1": "값", "B2": "값", ... }, ... }`
- 시트 찾기:
  - 시트명 정규화(`공백 제거 + 소문자`) 후 **완전일치 → 부분일치 → 첫 시트 fallback**
  - 디버깅 로그를 풍부하게 출력
- 셀 주소 A1을 0-based `{r,c}`로 변환 후 `api.setCellValue(r,c,value)`로 입력합니다.
- 중요한 수정 포인트:
  - 기존 `sheet.index` 대신 **`sheet.order`를 사용해** `setSheetActive(sheetOrder)`를 호출하도록 되어 있습니다.

---

### `prdinfo_tab.js` — 탭 전환/리사이즈 + 사전입력 폼 토글 + 재인증 조회
- 상단 탭(`.main-tab`) 클릭 시 컨텐츠를 전환합니다.
- 결과 탭으로 넘어갈 때 Luckysheet가 깨지지 않도록 `luckysheet.resize()` 및 `window.resize`를 강제로 트리거합니다.
- `ResizeObserver`로 결과 영역 크기 변경 시에도 리프레시를 수행합니다.
- 사전입력 폼 토글:
  - 클라우드 환경 구성(O/X)에 따라 세부 입력 영역 show/hide
  - 재계약(O/X)에 따라 재계약 입력 영역 show/hide
  - 보안성 면제(O/X)에 따라 상세 3개 영역 show/hide
- 재인증 조회:
  - 입력된 기존 인증번호를 `/lookup_cert_info/?cert_no=...`로 조회
  - 성공 시 결과 텍스트 영역에 `cert_id, product_name, total_wd`를 줄바꿈 포함하여 표시

---

### `prdinfo_download.js` — (서버 생성 방식) Luckysheet 값 수집 → `/download-filled/` POST → XLSX 다운로드
- `#btn-download` 클릭 시 실행됩니다.
- Luckysheet 내부 시트에서 다음을 **정확히 읽어** JSON으로 구성합니다.
  - `'제품 정보 요청'` 시트:
    - `B5~N5`, `B7~N7`
    - 단일 셀: `B9, D9, F9, G9, H9, J9, L9`
  - `'결함정보'` 시트:
    - `B4~O4`
- 셀 값 추출은 줄바꿈/리치텍스트를 최대한 보존하기 위해:
  - `cell.m`(표시 문자열, HTML 가능), `cell.ct.s`(rich text), `cell.v` 등을 순서대로 시도하고
  - `<br>`, `</p>` 같은 태그/엔티티를 `\n`로 변환합니다.
- CSRF 토큰을 input 또는 cookie에서 읽어 `X-CSRFToken`으로 전달합니다.
- 응답 blob을 받아 브라우저에서 파일 저장을 트리거합니다.
- 파일명은 `D5` 값 기반으로 안전하게 만들어 `"{D5}_제품 정보 요청 파일.xlsx"` 형태로 저장합니다.

---

## 3) JS 간 호출/의존 관계 그래프

- `prdinfo_generate.js`
  - → (의존) `prdinfo_fill_cells.js`의 `window.PrdinfoFill.apply()`
  - → (의존) `prdinfo_upload.js`가 세팅한 `#fileInput.files` (업로드 파일 목록)
  - → (간접) `prdinfo_tab.js`가 제공하는 사전입력 폼 값(같은 DOM에서 읽어옴)

- `prdinfo_tab.js`
  - → (연동) `/lookup_cert_info/` (prdinfo_db.py)

- `prdinfo_Luckysheet.js`
  - → (연동) `/source-excel/` (prdinfo_URL.py)
  - → (대안 다운로드) LuckyExcel export

- `prdinfo_download.js`
  - → (연동) `/download-filled/` (prdinfo_download.py)

---

## 4) 중요한 주의사항(실운영에서 헷갈리는 포인트)

### 4.1 `#btn-download` 이벤트 중복 가능성
- `prdinfo_Luckysheet.js`와 `prdinfo_download.js`가 **둘 다** `#btn-download` 클릭 이벤트를 등록합니다.
- 두 파일을 동시에 포함하면:
  - “클라이언트 export” + “서버 생성 다운로드”가 동시에 시도될 수 있고,
  - 사용자 경험/파일명/결과물이 꼬일 수 있습니다.

✅ 권장
- 다운로드 방식 하나만 선택해서 사용:
  - **서버 템플릿 기반(정확한 서식 유지)**이 필요하면: `prdinfo_download.js`만 사용
  - **간단히 export**만 필요하면: `prdinfo_Luckysheet.js`의 export만 사용

### 4.2 시트 활성화 기준: `order`
- `prdinfo_fill_cells.js`는 `sheet.index`가 아니라 `sheet.order`로 활성화합니다.
- Luckysheet 버전/데이터 구조에 따라 `index/order`가 다르게 동작할 수 있으니,
  추후 라이브러리 업데이트 시 이 부분이 가장 먼저 깨질 가능성이 있습니다.

---

## 5) 파일 목록(현재 문서가 다루는 대상)
- `prdinfo_Luckysheet.js`
- `prdinfo_upload.js`
- `prdinfo_generate.js`
- `prdinfo_fill_cells.js`
- `prdinfo_tab.js`
- `prdinfo_download.js`
