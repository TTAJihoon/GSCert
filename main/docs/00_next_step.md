# GSCert Next Step

이 문서는 전체 이력 보관용이 아니라 다른 PC에서 바로 이어가기 위한 직전 작업 인수인계 문서다.
상세 설계와 누적 이력은 `main/docs/`의 번호 문서와 각 폴더의 `readme.md`에 나누어 기록한다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 보안 페이지 URL: `http://127.0.0.1:8000/security/`
- 다운로드 검토 페이지 URL: `http://127.0.0.1:8000/download-review/`
- 서버 실행 예시: `.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- 다운로드 검토 테스트용 시작 가능 시간: 현재 `00:00-24:00`
- 운영 원복 마커: `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`
- 운영 기준 시간: `20:00-07:00`
- 숫자 prefix 설계 문서는 최상위 루트가 아니라 `main/docs/`에서 관리한다.

## 다른 개발 PC에서 시작하는 순서

1. 저장소를 받는다.

```powershell
git clone https://github.com/TTAJihoon/GSCert.git
cd GSCert
git switch codex-job-runner-persistence
git pull
```

이미 저장소가 있으면:

```powershell
git switch codex-job-runner-persistence
git pull
```

2. Codex skill을 설치한다.

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force `
  ".\main\docs\codex_skills\gscert-download-review-maintainer" `
  "$env:USERPROFILE\.codex\skills\gscert-download-review-maintainer"
```

3. 다음 문서를 먼저 읽고 이어간다.

- `main/docs/00_next_step.md`
- `main/docs/15_open_decisions.md`
- `main/docs/17_llm_review_interface.md`
- ECM 자동화 작업이면 `main/docs/03_webpage1_automation.md`
- 점검 규칙 구현이면 `main/docs/05_zip_inspection.md`
- skill이 설치되어 있으면 `gscert-download-review-maintainer`를 사용한다.

## 직전 작업

`/security/` 페이지의 AI 추천 수정 방안 팝업과 Invicti 분석 팝업 표시 오류를 수정했다.

- AI 추천 수정 방안 응답을 기존 일괄 응답에서 스트리밍 응답으로 추가했다.
  - 새 API: `POST /security/gpt/recommend/stream/`
  - 기존 API: `POST /security/gpt/recommend/` 유지
  - Gemini 스트리밍 helper: `generate_gemma_text_stream`
- Gemini/Gemma API 일시 오류 대응을 추가했다.
  - `500 INTERNAL`, `UNAVAILABLE` 같은 일시 서버 오류는 짧게 재시도한다.
  - `429`, `RESOURCE_EXHAUSTED`, quota/rate limit 계열은 호출 한도 오류로 분리한다.
  - 호출 한도 오류는 추가 재시도나 fallback 호출 없이 사용자에게 "AI 모델 호출 한도에 도달했습니다. 잠시 후 다시 시도해 주세요."로 표시한다.
  - 보안 추천은 `GEMINI_SECURITY_RETRIES`로 재시도 횟수를 조정할 수 있다.
  - 기본 fallback 모델은 `gemini-3.1-flash-lite`이며, `GEMINI_SECURITY_FALLBACK_MODELS` 또는 `GEMINI_FALLBACK_MODELS`로 바꿀 수 있다.
  - 기본 모델은 `GEMINI_SECURITY_MODEL`이 있으면 우선 사용하고, 없으면 `GEMINI_MODEL`을 사용한다.
- 프롬프트를 보완했다.
  - 첨부 보고서 내용을 무조건 결함으로 보지 않는다.
  - 실제 보안 결함이면 근거와 수정 방안을 제시한다.
  - 결함으로 보기 어렵다면 그 이유를 설명하고 불필요한 수정 방안을 제시하지 않는다.
  - 판단 불가하면 부족한 증거를 명확히 말한다.
- AI 추천 팝업에서 Markdown을 렌더링한다.
  - 제목, 목록, 표, 굵게, 기울임, 인라인 코드, 인용, 코드블록 지원
  - 응답 전체가 ```markdown 코드블록으로 감싸져 와도 바깥 fence를 제거한 뒤 렌더링한다.
  - 복사 버튼은 렌더링된 HTML이 아니라 원본 Markdown을 복사한다.
- AI 추천 팝업의 하단 다운로드 버튼을 Markdown 전용으로 변경했다.
  - AI 추천 팝업에서는 공용 모달 하단 버튼이 `MD 다운로드`로 표시되고 원본 Markdown `.md` 파일을 저장한다.
  - 응답 생성 전이나 오류 상태에서는 다운로드 버튼을 비활성화한다.
  - Invicti 분석 팝업을 다시 열면 같은 버튼이 `HTML 다운로드`로 복구되고 기존 HTML 저장 동작을 유지한다.
- AI 추천 팝업에 화면 표시용 typewriter 렌더링을 추가했다.
  - 이유: Gemini API가 큰 chunk로 응답하면 네트워크 스트리밍이 되어도 사용자는 한 번에 표시되는 것처럼 보일 수 있었다.
  - 이제 응답이 한 덩어리로 도착해도 UI가 조금씩 써 내려가듯 표시한다.
- AI 추천 팝업의 첫 응답 전 대기 UX를 보강했다.
  - 회전 인디케이터, 움직이는 진행바, 경과 시간, 단계 문구를 표시한다.
  - 첫 응답이 도착하면 자동으로 typewriter 출력으로 전환한다.
  - 이유: 모델이 첫 chunk를 늦게 반환하는 동안 한 줄짜리 로딩 문구만 보이면 멈춘 것처럼 느껴질 수 있었다.
- AI 추천 API가 끝까지 실패할 때는 `__GSCERT_AI_ERROR__:` 내부 마커로 내려보낸 뒤 요청 실패 UI로 표시한다.
  - 이유: 한글 `[오류]` 마커는 브라우저/콘솔 환경에 따라 깨질 수 있어 감지가 불안정했다.
- AI 추천 팝업 JS/CSS에 정적 파일 버전 쿼리를 붙였다.
  - 이유: 브라우저 캐시 때문에 스트리밍/Markdown 렌더링 코드가 반영되지 않는 문제가 있었다.
- 공용 모달 레이아웃을 `flex column` 구조로 보정했다.
  - 이유: 기존 `modalContent`가 `h-full`이고 하단 푸터가 별도로 붙어 있어 AI 팝업에서 콘텐츠와 푸터가 함께 80vh를 초과할 수 있었다.
- Invicti 분석 팝업의 펼침/닫힘 기능 사용 후 다른 팝업을 열 때 빈 화면이 보이는 문제를 수정했다.
  - Invicti 팝업은 Shadow DOM을 사용한다.
  - AI 팝업이 `#modalContent`를 교체할 수 있어 기존 ShadowRoot 참조가 stale 상태가 될 수 있었다.
  - 팝업 닫기와 재오픈 시 ShadowRoot/host를 초기화하도록 변경했다.
- AI 추천 팝업을 본 뒤 Invicti 분석 팝업을 다시 열면 내용이 비어 보일 수 있는 상태 충돌을 정리했다.
  - 공용 모달의 닫기 핸들러와 내부 상태를 현재 팝업 소유자 기준으로 정리한다.
  - AI 팝업을 열 때 Invicti Shadow DOM 상태를 해제하고, Invicti 팝업을 열 때 AI typewriter 상태를 해제한다.
- Invicti 보고서에서 `container-fluid` 상위 컨테이너가 없는 취약점도 원본 HTML 스니펫을 만들도록 수정했다.
  - 확인 샘플: `gs.docuops.ngrok.app - 상세 스캔 보고서.html`
  - 증상: 5번 `약한 암호가 사용되었습니다.` 항목의 `invicti_analysis`가 빈 값이라 팝업이 비어 있었다.
  - 수정 후 해당 항목에 약한 암호 목록이 포함된 HTML 스니펫이 생성된다.

## 변경 파일

- `main/utils/gemini_gemma.py`
- `main/views/testing/security_GPT.py`
- `main/urls.py`
- `main/static/scripts/testing/security_GPT_popup.js`
- `main/static/scripts/testing/security_invicti_popup.js`
- `main/static/css/testing/security_GPT.css`
- `main/templates/testing/security.html`
- `main/views/testing/security_extractHTML.py`

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\testing\security_GPT.py main\utils\gemini_gemma.py
.\.venv\Scripts\python.exe -m py_compile main\views\testing\security_extractHTML.py
node --check main\static\scripts\testing\security_GPT_popup.js
node --check main\static\scripts\testing\security_invicti_popup.js
.\.venv\Scripts\python.exe manage.py check
```

추가로 로컬 서버를 실행한 뒤 다음을 확인했다.

- `GET /security/` 응답 200
- `POST /security/gpt/recommend/stream/` 응답 200 및 streaming 응답 확인
- Chromium 자동화로 실제 페이지 팝업 흐름 확인
  - 샘플 HTML 업로드 후 5개 행 렌더링
  - 5번 `약한 암호가 사용되었습니다.` Invicti 팝업에서 `TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA` 표시 확인
  - Invicti 분석 팝업 열기
  - 취약점 URL 펼침/닫힘 토글
  - 탭 전환
  - 팝업 닫기 후 AI 추천 팝업 열기
  - Markdown 표와 굵게 렌더링 확인
  - 다시 Invicti 분석 팝업 열기
  - AI 팝업 스트리밍 중간 상태와 최종 Markdown 렌더링 확인
  - AI 응답을 일부러 지연시켜 로딩 인디케이터, 진행바, 경과 시간 갱신 확인
  - Gemini/Gemma 가짜 클라이언트로 `500 INTERNAL` 후 retry/fallback 호출 순서 확인
  - Gemini/Gemma 가짜 클라이언트로 `429 RESOURCE_EXHAUSTED`는 추가 호출 없이 호출 한도 오류로 분리되는 것 확인
  - `AI 추천 > 닫기 > Invicti 분석` 순서 확인
  - `Invicti 분석 > 닫기 > AI 추천 > 닫기 > Invicti 분석` 순서 확인
  - `security_GPT_popup.js?v=20260522e`, `security_invicti_popup.js?v=20260522e`, `security_GPT.css?v=20260522b` 로드 확인
  - AI 추천 팝업에서 `MD 다운로드` 버튼이 `.md` 파일을 생성하고, Invicti 팝업으로 전환하면 `HTML 다운로드`로 복구되는지 확인

## 바로 다음 작업

1. `/security/` 페이지에서 실제 보고서 데이터로 AI 추천 스트리밍 체감 속도와 응답 품질을 확인한다.
   - 추천: 먼저 짧은 결함 1건, 결함이 아닌 항목 1건, 판단이 애매한 항목 1건으로 비교한다.
   - 이유: 프롬프트가 결함/비결함/판단불가를 잘 나누는지 빠르게 확인할 수 있다.
2. 스트리밍 응답이 느리면 모델, 전달 context 길이, UI 표시 단위를 조정한다.
   - 추천: 모델 변경보다 먼저 프롬프트와 전달 본문 길이를 줄인다.
   - 이유: 품질 저하 없이 체감 속도를 개선할 가능성이 가장 높다.
3. 실제 점검 규칙 18개 초안을 작성한다.
   - 추천: 각 규칙을 `대상 파일`, `확인 기준`, `통과 조건`, `실패 조건`, `판단불가 조건`, `LLM 사용 여부`로 먼저 분해한다.
   - 이유: 프로그램 규칙과 LLM 규칙을 안정적으로 나눌 수 있다.
4. 영남 live 다운로드를 실제 프로젝트 1건으로 검증한다.
   - 후보: `TTA-26-00200`
   - 확인 기준: `영남AX센터 > {연도} 인증시험서비스 > 01 GS인증시험(1등급) > 프로젝트폴더`
5. 다운로드 검토 테스트가 끝나면 시간 제한을 운영 기준으로 원복한다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 결정 필요

현재 푸시 전에 추가로 결정해야 할 항목은 없다.
