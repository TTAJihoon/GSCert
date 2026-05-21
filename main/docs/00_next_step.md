# Download Review Next Step

이 문서는 전체 이력 보관용이 아니라 다른 PC에서 바로 이어가기 위한 직전 작업 인수인계 문서다.
상세 설계와 누적 이력은 `main/docs/`의 번호 문서와 각 폴더의 `readme.md`에 나누어 기록한다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
- 로컬 URL: `http://127.0.0.1:8000/download-review/`
- 서버: `manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings`
- 테스트용 시작 가능 시간: 현재 `00:00-24:00`
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

3. 새 Codex 대화에서 아래 순서로 읽고 이어간다.

- `main/docs/00_next_step.md`
- `main/docs/15_open_decisions.md`
- `main/docs/17_llm_review_interface.md`
- 실제 작업이 ECM 자동화면 `main/docs/03_webpage1_automation.md`
- 실제 작업이 규칙 구현이면 `main/docs/05_zip_inspection.md`
- skill을 설치했다면 `gscert-download-review-maintainer`를 사용한다.

## 직전 작업

`/similar/` 유사도 검색에 LLM 재평가 단계를 추가했다.

- 자동 입력은 파일 파싱 후 LLM 요약을 만들고, 수동 입력은 입력한 요약 문장을 그대로 검색 기준으로 사용한다.
- FAISS로 후보 100개를 먼저 조회한다.
- 기존 요약 프롬프트가 있는 `main/views/testing/similar_GPT.py`에 공통 LLM 재평가 프롬프트를 추가했다.
  - 입력 문장에서 핵심 기능/기술/도메인과 감점해야 할 일반 표현을 내부적으로 판단하게 한다.
  - 후보 100개 중 실제 목적과 핵심 기능이 가까운 상위 30개만 JSON으로 반환하게 한다.
  - LLM에는 후보별 `id`와 원문 `제품설명`만 전달한다.
  - LLM 응답은 `id`와 `score`만 받는다.
- 재평가 기본 모델은 `gemini-3.1-flash-lite`다.
  - `GEMINI_RERANK_MODEL` 환경변수로 덮어쓸 수 있다.
- 화면에는 LLM 점수 기준 `AI 유사도`를 표시한다.
- LLM 재평가 실패 또는 API 키 미설정 시 FAISS 상위 30개로 fallback한다.
- LLM이 30개보다 적게 반환하면 부족한 항목은 FAISS 순위로 채운다.
- FAISS 인덱스와 `SentenceTransformer` 모델은 서버 프로세스 메모리에 캐시한다.
  - 서버 재시작 후 첫 검색은 모델 로드 때문에 느릴 수 있다.
  - 같은 서버 프로세스의 두 번째 검색부터는 캐시를 사용한다.

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\testing\similar_compare.py main\views\testing\similar_summary.py
.\.venv\Scripts\python.exe -m py_compile main\views\testing\similar_GPT.py
node --check main\static\scripts\testing\similar_submit.js
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
```

현재 로컬에서 `GEMINI_API_KEY`와 `gemini-3.1-flash-lite` 재평가 호출을 검증했다.

수동 입력 LLM 재평가 성능 측정:

```text
서버 재시작 후 1회차: 19.43초
캐시 이후 2회차: 8.78초
```

## 바로 다음 작업

1. 실제 점검 규칙 18개를 규칙 정의 양식으로 작성한다.
   - 대상 파일
   - 확인 기준
   - 통과 조건
   - 실패 조건
   - 판단불가 조건
   - 프로그램 규칙/LLM 후보 여부
2. 영남 live 다운로드를 실제 프로젝트 1건으로 검증한다.
   - 후보: `TTA-26-00200`
   - ECM 트리가 `영남AX센터 > {연도}년 시험서비스 > 01 GS인증시험(1등급) > 프로젝트폴더` 순서로 열리는지 확인한다.
3. Codex 수동 테스트가 필요한 규칙은 `build_llm_review_prompt`로 payload를 만들고 이 대화에 붙여 넣어 응답 품질을 확인한다.
4. API 환경이 준비되면 provider adapter를 추가한다.
5. 테스트가 끝나면 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`
6. 검색/임베딩 기능을 사용하는 PC에서는 `requirements-search.txt`를 별도로 설치한다.
7. `/similar/` 첫 검색 지연이 업무상 불편하면 서버 시작 후 모델을 미리 로드하는 prewarm 방식을 추가한다.
8. `STT/TTS API` 같은 입력으로 LLM 재평가 품질을 브라우저에서 확인한다.

## 최근 결정

1. LLM 적용 범위는 단순 규칙 전체가 아니라 문서 본문 의미 판단이 필요한 규칙으로 제한한다.
   - 단순 파일 존재/확장자/파일명 규칙은 프로그램 규칙으로 구현한다.
   - 이유: 프로그램 규칙이 더 빠르고 재현성이 높으며, LLM 비용과 보안 검토 범위를 줄일 수 있다.
2. LLM 수동 테스트에 사용할 문서 본문은 먼저 텍스트 context 파일로 제공하고, 이후 Word/PDF 추출기를 붙인다.
   - 이유: 규칙 프롬프트 품질 검증과 문서 추출 오류를 분리할 수 있다.
3. 수동 테스트 대상은 Claude로 고정하지 않는다.
   - 현재 대화의 Codex에게 payload를 전달해 테스트할 수 있고, 나중에 API를 붙일 때도 같은 payload 흐름을 사용한다.
4. 기본 ECM 다운로드 방식은 전체 선택으로 유지한다.
   - 다른 선택 방식은 skill 지침에만 두고, 실제 필요가 생기면 코드화한다.
5. UI 목업 전용 requirements는 제거하고 기본 서버 requirements로 통일한다.
   - 이유: 현재 UI가 API/DB 흐름을 사용하므로 Django 단독 설치 기준이 실제 실행 조건과 맞지 않는다.
6. FAISS/임베딩/형태소 분석 의존성은 별도 requirements로 분리한다.
   - 이유: 기본 웹서버 설치를 무겁게 만들지 않고, 검색 기능이 필요한 환경에서만 설치하기 위해서다.
7. `/similar/` 수동 입력은 요약문 직접 입력으로 본다.
   - 이유: 수동 입력에서도 LLM 요약을 호출하면 자동 입력 대비 시간 절감 효과가 사라진다.
8. `/similar/` 정렬 품질은 FAISS 단독이 아니라 FAISS 후보 100개 + LLM top 30 재평가 방식으로 높인다.
   - 이유: STT/TTS처럼 핵심 기술어가 중요한 입력에서 일반 API/데이터 관리 문장이 상위로 섞이는 문제를 줄이기 위해서다.

## 결정 필요

1. 실제 점검 규칙 초안을 작성해야 한다.
   - 추천: 산출물 컬럼별로 "대상 파일, 확인 기준, 통과 조건, 실패 조건, 판단불가 조건"을 먼저 적는다.
   - 이유: 이 정보가 있어야 프로그램 규칙과 LLM 규칙을 나누고, LLM prompt도 안정적으로 만들 수 있다.
2. API 환경이 준비되면 provider adapter 설정값을 정해야 한다.
   - 추천: provider, endpoint, model, timeout, retry, max token, key 환경변수명을 먼저 정한다.
   - 이유: 상용 API와 내부 GPU API를 같은 인터페이스로 바꾸려면 설정 경계가 명확해야 한다.
