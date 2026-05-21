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

`/security/` 페이지의 AI 추천 수정 방안 팝업과 Invicti 분석 팝업 재오픈 오류를 수정했다.

- AI 추천 수정 방안 응답을 기존 일괄 응답에서 스트리밍 응답으로 추가했다.
  - 새 API: `POST /security/gpt/recommend/stream/`
  - 기존 API: `POST /security/gpt/recommend/` 유지
  - Gemini 스트리밍 helper: `generate_gemma_text_stream`
- 프롬프트를 보완했다.
  - 첨부 보고서 내용을 무조건 결함으로 보지 않는다.
  - 실제 보안 결함이면 근거와 수정 방안을 제시한다.
  - 결함으로 보기 어렵다면 그 이유를 설명하고 불필요한 수정 방안을 제시하지 않는다.
  - 판단 불가하면 부족한 증거를 명확히 말한다.
- AI 추천 팝업에서 Markdown을 렌더링한다.
  - 제목, 목록, 표, 굵게, 기울임, 인라인 코드 지원
  - 복사 버튼은 렌더링된 HTML이 아니라 원본 Markdown을 복사한다.
- Invicti 분석 팝업의 펼침/닫힘 기능 사용 후 다른 팝업을 열 때 빈 화면이 보이는 문제를 수정했다.
  - Invicti 팝업은 Shadow DOM을 사용한다.
  - AI 팝업이 `#modalContent`를 교체할 수 있어 기존 ShadowRoot 참조가 stale 상태가 될 수 있었다.
  - 팝업 닫기와 재오픈 시 ShadowRoot/host를 초기화하도록 변경했다.

## 변경 파일

- `main/utils/gemini_gemma.py`
- `main/views/testing/security_GPT.py`
- `main/urls.py`
- `main/static/scripts/testing/security_GPT_popup.js`
- `main/static/scripts/testing/security_invicti_popup.js`
- `main/static/css/testing/security_GPT.css`

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\testing\security_GPT.py main\utils\gemini_gemma.py
node --check main\static\scripts\testing\security_GPT_popup.js
node --check main\static\scripts\testing\security_invicti_popup.js
.\.venv\Scripts\python.exe manage.py check
```

추가로 로컬 서버를 실행한 뒤 다음을 확인했다.

- `GET /security/` 응답 200
- `POST /security/gpt/recommend/stream/` 응답 200 및 streaming 응답 확인
- Chromium 자동화로 실제 페이지 팝업 흐름 확인
  - Invicti 분석 팝업 열기
  - 취약점 URL 펼침/닫힘 토글
  - 탭 전환
  - 팝업 닫기 후 AI 추천 팝업 열기
  - Markdown 표와 굵게 렌더링 확인
  - 다시 Invicti 분석 팝업 열기

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
