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

## 직전 작업

LLM 기반 점검을 나중에 붙일 수 있도록 provider-neutral 인터페이스와 Codex/LLM 수동 테스트 경로를 추가했다.

- `main/views/review/ecm_llm_review.py`를 추가했다.
  - 프로젝트 정보, 파일 목록, 규칙 프롬프트를 LLM payload로 구성한다.
  - Claude/GPT/Gemini/내부 GPU API에 공통으로 넘길 수 있는 `messages`를 만든다.
  - 모델 응답 JSON schema를 제공한다.
  - 모델 응답을 `pass/fail/warning/error`로 파싱한다.
- `main/management/commands/build_llm_review_prompt.py`를 추가했다.
  - 실제 API key 없이 다운로드 폴더 기준 LLM 테스트 payload를 생성한다.
  - 생성된 JSON의 `messages`를 현재 Codex 대화나 다른 LLM에 붙여 넣어 수동 테스트할 수 있다.
- `main/docs/17_llm_review_interface.md`를 추가했다.
  - 현재는 실제 API 호출, API key, endpoint, Word/PDF 본문 추출, worker 자동 연결은 하지 않는다.
  - 실제 provider adapter는 API 환경이 준비된 뒤 추가한다.
- `main/tests.py`에 `LlmReviewInterfaceTests`를 추가했다.
- 로컬 Codex skill `gscert-download-review-maintainer` 참고 문서도 LLM 인터페이스 기준으로 갱신한다.

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_llm_review.py main\management\commands\build_llm_review_prompt.py
.\.venv\Scripts\python.exe manage.py test main.tests.LlmReviewInterfaceTests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe C:\Users\jh910\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\jh910\.codex\skills\gscert-download-review-maintainer
```

## 바로 다음 작업

1. 영남 live 다운로드를 실제 프로젝트 1건으로 검증한다.
   - 후보: `TTA-26-00200`
   - ECM 트리가 `영남AX센터 > {연도}년 시험서비스 > 01 GS인증시험(1등급) > 프로젝트폴더` 순서로 열리는지 확인한다.
2. 실제 산출물별 규칙을 정의한다.
   - 단순 존재/파일명/확장자 규칙은 기존 프로그램 규칙으로 구현한다.
   - 본문 해석이 필요한 규칙만 LLM 수동 테스트 후보로 분리한다.
3. Codex 수동 테스트가 필요한 규칙은 `build_llm_review_prompt`로 payload를 만들고 이 대화에 붙여 넣어 응답 품질을 확인한다.
4. API 환경이 준비되면 provider adapter를 추가한다.
5. 테스트가 끝나면 시간 제한을 운영 기준으로 되돌린다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 최근 결정

1. LLM 적용 범위는 단순 규칙 전체가 아니라 문서 본문 의미 판단이 필요한 규칙으로 제한한다.
   - 단순 파일 존재/확장자/파일명 규칙은 프로그램 규칙으로 구현한다.
   - 이유: 프로그램 규칙이 더 빠르고 재현성이 높으며, LLM 비용과 보안 검토 범위를 줄일 수 있다.
2. LLM 수동 테스트에 사용할 문서 본문은 먼저 텍스트 context 파일로 제공하고, 이후 Word/PDF 추출기를 붙인다.
   - 이유: 규칙 프롬프트 품질 검증과 문서 추출 오류를 분리할 수 있다.
3. 수동 테스트 대상은 Claude로 고정하지 않는다.
   - 현재 대화의 Codex에게 payload를 전달해 테스트할 수 있고, 나중에 API를 붙일 때도 같은 payload 흐름을 사용한다.

## 결정 필요

1. 실제 점검 규칙 초안을 작성해야 한다.
   - 추천: 산출물 컬럼별로 "대상 파일, 확인 기준, 통과 조건, 실패 조건, 판단불가 조건"을 먼저 적는다.
   - 이유: 이 정보가 있어야 프로그램 규칙과 LLM 규칙을 나누고, LLM prompt도 안정적으로 만들 수 있다.
2. API 환경이 준비되면 provider adapter 설정값을 정해야 한다.
   - 추천: provider, endpoint, model, timeout, retry, max token, key 환경변수명을 먼저 정한다.
   - 이유: 상용 API와 내부 GPU API를 같은 인터페이스로 바꾸려면 설정 경계가 명확해야 한다.
