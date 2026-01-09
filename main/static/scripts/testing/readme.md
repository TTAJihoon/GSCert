# testing 프론트엔드(JS) 코드 구성 요약 (History / Security / Similar)

이 문서는 `testing` 기능(History/ Security/ Similar)과 연동되는 **프론트엔드 JS 11개**를 대상으로,
각 파일의 역할과 **서로의 호출/의존 관계**, 그리고 **Django 백엔드(Python 뷰)**와의 연동 포인트를 정리합니다.

구분
- **History**: 시험 이력 조회 + ECM 자동 다운로드(WebSocket)
- **Security**: Invicti HTML 기반 보안성 결함리포트 자동작성 + 표 편집/팝업 + GPT 추천
- **Similar**: 파일/수동입력 기반 제품 요약 + 유사 제품 조회 + 정렬

---

## 0) 엔드포인트(백엔드) 연동 맵

| 기능 | 호출 JS | Endpoint | 방식 | 백엔드(대응 py) | 응답/효과 |
|---|---|---|---|---|---|
| 유사 제품 요약/검색 | `similar_submit.js` | `/summarize_document/` | POST(FormData) | `similar_summary.py` | `{summary, response, similarities}` |
| Invicti HTML 파싱 | `security_submit.js` | `/security/invicti/parse/` | POST(FormData) | `security.py` → `security_extractHTML.py` | `{css, rows, ...}` |
| GPT 추천 수정 방안 | `security_GPT_popup.js` | `/security/gpt/recommend/` | POST(JSON) | `security_GPT.py` | `{response}` |
| ECM 자동 다운로드 작업 | `history_ECM.js` | `/ws/run_job/` | WebSocket(JSON) | Channels consumer(Playwright job) | `wait/processing/success(url)/error` |

---

## 1) History: 시험 이력 조회 + ECM 자동 다운로드

### 1.1 `history_Listener.js` — 검색 조건 최소 1개 입력 검증
- `#queryForm` submit 시,
  - `gsnum/project/company/product/comment` 다 비어 있으면 submit을 막고 알림을 띄웁니다.
- 목적: “조건 없이 전체 조회” 같은 부담 큰 쿼리를 방지.

**의존/호출**
- 독립 스크립트 (백엔드 호출 없음)

---

### 1.2 `history_set_date.js` — 기간 버튼(예: 10년)으로 시작/종료일 자동 세팅
- DOMContentLoaded 시 `#ten-years-btn`를 자동 클릭합니다.
- `setYearsAgo(years)`:
  - `#start_date`를 “오늘 기준 N년 전”
  - `#end_date`를 “오늘”
  - `yyyy-mm-dd` 형식으로 맞춰 설정합니다.

**의존/호출**
- 독립 스크립트 (백엔드 호출 없음)

---

### 1.3 `history_ECM.js` — ECM “시험성적서 다운로드” 자동화(WebSocket)
- 테이블 내 `.download-btn` 클릭을 **이벤트 위임**으로 감지합니다.
- 클릭된 버튼이 속한 row(tr)에서:
  - 테이블 header를 기준으로 `인증일자`, `시험번호` 컬럼 인덱스를 찾아 값 추출
  - (header를 못 찾으면 fallback 인덱스 사용)
- WebSocket(`/ws/run_job/`)을 **버튼 클릭마다 새로 열어** payload 전송 후,
  서버 메시지 상태에 따라 UI를 갱신합니다.
  - `wait`: 대기열 정보가 있으면 “내 순번/내 앞 대기 수”를 보여줌
  - `processing`: ECM 자동화 실행 중 문구
  - `success`: `url`을 받으면 새 탭으로 `window.open(url)` 실행(중복 open 방지 set 유지)
  - `error`: alert 표시
- 로딩 영역:
  - `#loadingIndicator`, `#loadingText`를 on/off, 문구 갱신

**의존/호출**
- (프론트) `.download-btn` 클릭 → WebSocket `/ws/run_job/` 호출
- (백엔드) consumer가 `success:url`을 보내면 새 탭 오픈

---

## 2) Security: 보안성 결함리포트(Invicti) 자동 작성 + 편집/팝업 + GPT

> Security 영역은 공통 전역 네임스페이스를 씁니다: `window.SecurityApp`  
> 파일들이 서로를 함수로 “직접 import”하는 구조가 아니라, **전역 객체에 기능을 꽂아 넣고 HTML onclick에서 호출**하는 패턴입니다.

### 2.1 `security_editable.js` — 테이블 렌더/편집/선택(체크박스)/데이터 주입의 “코어”
- `SecurityApp.state` 전역 상태를 초기화:
  - `currentData[]`, `selectedRows(Set)`, `isEditing`, `editingCell`
- 스키마(`SecurityApp.schema.fields`)로 컬럼 정의:
  - 체크박스, select(결함정도 H/M/L, 발생빈도 A/I), textarea(요약/설명), popup(Invicti 분석 / GPT 추천)
- 렌더링:
  - `renderTableHeader()`, `renderTable()`가 header/body를 생성
  - popup 컬럼은 버튼 생성 후 `onclick="SecurityApp.popup.showInvictiAnalysis(...)"`,
    `onclick="SecurityApp.gpt.getGptRecommendation(...)"` 형태로 전역 함수 호출을 연결
- 셀 편집:
  - `startEdit()`로 textarea/select UI를 셀 내부에 주입
  - blur 또는 Enter 저장, Escape 취소
- 선택:
  - 행 checkbox 선택/전체선택 토글, 선택 행 하이라이트
- 외부에서 파싱 결과 rows를 주입하는 API 제공:
  - `SecurityApp.setData(rows)`, `SecurityApp.clearData()`
- 토스트 UI:
  - `showSuccess/showError` (우측 상단 toast)

**의존/호출**
- `security_submit.js`가 `setData(rows)`를 호출해 데이터를 주입
- `security_button.js`가 `SecurityApp.state.selectedRows`, `renderTable()` 등을 사용
- popup 버튼은 `security_invicti_popup.js`, `security_GPT_popup.js`에 정의된 전역 함수를 호출

---

### 2.2 `security_button.js` — 상단 버튼(추가/삭제/엑셀다운로드) + 선택 UI
- 버튼 바인딩:
  - `#exportBtn`: 현재 `currentData`를 XLSX로 내려받기(`XLSX.writeFile`)
  - `#deleteSelectedBtn`: 체크된 행 삭제
  - `#addRowBtn`: 새 행 기본값으로 추가
- 선택 UI:
  - 선택된 행 수를 `#selectedCount`에 표시
  - `#selectAll`의 checked/indeterminate 상태를 현재 선택 수에 따라 갱신

**의존/호출**
- `SecurityApp.state.currentData`, `selectedRows` 사용
- `SecurityApp.renderTable()`, `SecurityApp.updateTotalCount()` 호출
- XLSX 라이브러리 의존(페이지에 XLSX 스크립트 필요)

---

### 2.3 `security_submit.js` — Invicti HTML 업로드 UI + `/security/invicti/parse/` 호출
- 업로드 UX:
  - 드래그&드롭 / 클릭 선택
  - `.html/.htm`만 허용
  - 중복 파일 제거(이름+사이즈+lastModified)
  - 내부 `currentFiles[]`를 `<input type=file>`에 `DataTransfer`로 동기화
  - 파일 목록 렌더 + 개별 삭제(이벤트 위임)
- “자동 작성” 버튼(`#btn-generate`) 클릭 시:
  - FormData에 html 파일들을 append
  - CSRF 토큰을 form hidden input 또는 cookie에서 추출
  - `/security/invicti/parse/`로 POST
  - 성공 시:
    - `json.css`를 `<style id="invicti-dynamic-styles">`로 head에 주입(Invicti 원본 스타일)
    - `SecurityApp.state.reportCss = css` 저장(팝업에서 재사용)
    - rows에 id 없으면 `generateId()`로 보강 후 `SecurityApp.setData(rows)` 호출
  - 실패 시 `SecurityApp.clearData()` 후 에러 토스트

**의존/호출**
- `security_editable.js`가 제공하는 `generateId/setData/clearData/showSuccess/showError` 필요
- 백엔드: `security.py` → `security_extractHTML.py` 결과(`rows`, `css`) 전제

---

### 2.4 `security_invicti_popup.js` — Invicti 분석 팝업(Shadow DOM 격리) + HTML/ZIP 다운로드
- 공개 함수:
  - `SecurityApp.popup.showInvictiAnalysis(rowId)` (테이블의 “Invicti 분석” 버튼에서 호출)
- 주요 특징:
  - 모달 DOM이 없으면 동적으로 생성(80vw/80vh)
  - Invicti 원본 CSS(`invicti-dynamic-styles`)를 **팝업 동안 disabled** 처리해 전역 레이아웃 누수 방지
  - 팝업 내부는 **Shadow DOM**에 렌더링하여 외부 스타일과 충돌 최소화
  - Invicti HTML 내 상호작용 보정:
    - `.vuln-url` 클릭 시 URL 리스트 토글
    - `.vuln-tabs` 탭 전환 로직
  - “HTML 다운로드”:
    - 원본 CSS + 보정 CSS + 상호작용 스크립트를 포함한 단일 HTML로 저장
  - “전체 ZIP 다운로드”:
    - `JSZip`이 존재하면 모든 row의 invicti_analysis를 html로 만들어 zip으로 저장

**의존/호출**
- `security_submit.js`가 저장한 `SecurityApp.state.reportCss` 사용
- rows의 `invicti_analysis`, `invicti_report`가 백엔드 파싱 결과에 포함되어 있어야 함
- JSZip 라이브러리(옵션), 모달 DOM(#modal)이 없으면 자동 생성

---

### 2.5 `security_GPT_popup.js` — GPT 추천 수정 방안 팝업 + 결과 캐시
- 공개 함수:
  - `SecurityApp.gpt.getGptRecommendation(rowId)` (테이블의 “GPT 추천” 버튼에서 호출)
- 동작:
  1) rowId로 `SecurityApp.state.currentData`에서 row 찾기
  2) `row.gpt_response`가 이미 있으면 즉시 표시(캐시)
  3) `row.gpt_prompt`가 없으면 오류 표시
  4) `/security/gpt/recommend/`로 `{prompt: row.gpt_prompt}` POST
  5) 성공 시:
     - `row.gpt_response = result.response`로 캐시
     - 모달에 응답 표시(복사 버튼 포함)
- 모달 처리:
  - 기존 모달 컨텐츠 영역이 shadowRoot를 가진 경우 충돌을 감지하고 content host를 재생성

**의존/호출**
- `security_extractHTML.py`가 생성한 `gpt_prompt`가 row에 있어야 정상 동작
- 백엔드: `security_GPT.py`의 추천 API
- clipboard API(복사) 사용

---

## 3) Similar: 유사 제품 조회(요약 + 결과 표시 + 정렬)

### 3.1 `similar_Listener.js` — 탭(자동/수동) 전환 + 파일 업로드 UI
- 탭:
  - `#tab-auto` / `#tab-manual` 클릭으로 `#content-auto/#content-manual` show/hide
- 업로드:
  - dropArea 클릭/drag&drop으로 파일 선택
  - 허용 확장자: `docx, xlsx, pdf, pptx, txt`
  - 업로드 후 파일명 표시, remove 버튼으로 초기화
  - drag&drop 시 `DataTransfer`로 `fileInput.files`를 동기화

**의존/호출**
- 독립 UI 스크립트(백엔드 호출 없음)
- 실제 서버 요청은 `similar_submit.js`에서 수행

---

### 3.2 `similar_submit.js` — `/summarize_document/` 호출 + 결과 카드 렌더링 (본 대화에서 제공된 코드)
- `#queryForm` submit을 완전히 차단(`e.preventDefault()`)
- 자동 탭이면 파일 필수, 수동 탭이면 textarea 입력 필수
- 로딩 표시:
  - `#loadingContainer` show/hide
  - 결과 헤더/요약/결과 영역 hidden 토글
- 전송(FormData):
  - 자동 탭: `fileType=functionList`, `file=<업로드파일>`, `manualInput=''`
  - 수동 탭: `fileType=manual`, `file=''`, `manualInput=<텍스트>`
  - CSRF 토큰은 cookie에서 읽어 `X-CSRFToken` 헤더로 전달
- 응답 처리:
  - `data.summary`를 `#summaryContent`에 표시
  - `data.response[]`를 map하여 유사 제품 카드 DOM 생성
  - 각 row의 `similarity`를 %로 변환해서 `유사도 78.23%` 표시

**의존/호출**
- 백엔드: `similar_summary.py`(요약+검색) 결과 포맷에 의존

---

### 3.3 `similar_sorting.js` — 화면에 렌더된 유사 제품 카드 정렬(날짜/유사도)
- `#sortByDateBtn`:
  - 카드 내 `인증일자` 값을 Date로 파싱해 정렬(토글: 오름/내림)
- `#sortBySimilarityBtn`:
  - 카드 내 `.similarity-score`에서 `%` 숫자만 파싱해 정렬(토글)
- 정렬은 DOM element를 다시 append하는 방식으로 수행

**의존/호출**
- `similar_submit.js`가 만든 `.similar-product` DOM 구조에 의존

---

## 4) 호출/의존 그래프(요약)

### History
- `history_set_date.js` (초기 기간 자동세팅)
- `history_Listener.js` (submit 입력 검증)
- `history_ECM.js` (버튼 클릭 → WebSocket → url 새 탭 오픈)

### Security (`window.SecurityApp` 기반 결합)
1. `security_editable.js` (state/schema/render/edit/select, setData/clearData 제공)
2. `security_button.js` (추가/삭제/엑셀, 선택 UI 갱신)
3. `security_submit.js` (HTML 업로드 → `/security/invicti/parse/` → setData)
4. `security_invicti_popup.js` (row.invicti_analysis 팝업/다운로드)
5. `security_GPT_popup.js` (row.gpt_prompt → `/security/gpt/recommend/` → row.gpt_response 캐시)

### Similar
- `similar_Listener.js` (탭/업로드 UI)
- `similar_submit.js` (submit → `/summarize_document/` → 결과 렌더)
- `similar_sorting.js` (렌더된 결과 정렬)

---

## 5) 실운영 체크 포인트(짧게)

- **SecurityApp 전역 결합**
  - 파일 로드 순서가 중요합니다.
  - 최소한 `security_editable.js`가 먼저 로드되어 `SecurityApp.setData/renderTable` 등이 준비된 뒤
    `security_submit.js`, `security_button.js`, 팝업들이 동작하는 구조가 안전합니다.

- **Security 다운로드**
  - `security_button.js`의 엑셀 다운로드는 XLSX 의존이므로, 페이지에 `XLSX` 스크립트가 없으면 오류가 납니다.

- **History WebSocket**
  - 서버가 `success`에 `url`을 반드시 포함해야 새 탭 오픈이 됩니다.
  - 테이블 헤더명이 바뀌면(`인증일자/시험번호`) 컬럼 탐지가 실패할 수 있어 fallback 인덱스가 중요합니다.

- **Similar 정렬**
  - `similar_sorting.js`는 DOM 텍스트 기반 파싱이므로, 카드 마크업(라벨 텍스트)이 바뀌면 정렬이 깨질 수 있습니다.
