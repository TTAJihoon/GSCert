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
- 점검 규칙 구현이면 `main/docs/05_zip_inspection.md`
- LLM 규칙 검토가 필요하면 `main/docs/17_llm_review_interface.md`
- ECM 자동화 작업이면 `main/docs/03_webpage1_automation.md`
- 기존 시험 이력/유사 시험 ECM 버튼을 서버 파일 캐시 방식으로 바꾸는 검토는 `main/docs/ecm_download_issue/readme.md`
- skill이 설치되어 있으면 `gscert-download-review-maintainer`를 사용한다.

## 직전 작업

산출물 점검 규칙 1~7번의 실제 규칙 정의를 문서화했다.

- `05_zip_inspection.md`에 실제 규칙 정의 초안을 추가했다.
- `15_open_decisions.md`의 검사 규칙 설계 상태를 최신화했다.
- `02_database_design.md`에 `ecm_list.WD` 기준 컬럼을 추가했다.

확정된 규칙:

1. 계약서
2. 합의서
3. 수수료산정표
4. 시험환경구성도
5. 품질특성별제품정보기재사항
6. 기능리스트
7. 시험계획서

주요 확정사항:

- 모든 파일명 조건은 단어 순서와 관계없이 필요한 단어가 모두 포함되는지만 검사한다.
- 폴더 조건을 만족하는 폴더는 1개뿐이라는 전제로 첫 매칭 폴더에서 진행한다.
- `{프로젝트번호}`는 `ecm_list.프로젝트번호`에서 읽는다.
- `{제품명}`은 `ecm_list.제품명`에서 읽는다.
- `{PL}`은 `ecm_list.시험PL`에서 읽는다.
- `{WD}`는 새로 추가될 `ecm_list.WD`에서 읽는다.
- 시험계획서의 `{버전}`은 `{제품명}`에서 `ver`, `Ver`, `v`, `V`로 시작하는 부분부터 마지막까지 추출한다.
- 시험계획서의 `<세부사양>` 표 비교는 13번 시험결과서 규칙이 정의된 후 다시 확정한다.
- 현재 확정된 1~7번 규칙은 LLM 없이 파일 탐색, Word/Excel/PDF 파싱, 표/셀 값 비교로 처리 가능하다.

## 변경 파일

- `main/docs/00_next_step.md`
- `main/docs/02_database_design.md`
- `main/docs/05_zip_inspection.md`
- `main/docs/15_open_decisions.md`

## 검증 완료

문서 변경만 수행했다.

```powershell
git diff --check
```

## 바로 다음 작업

1. 8~18번 산출물 점검 규칙을 같은 형식으로 정의한다.
   - 추천: 한 번에 3~5개씩 정의한다.
   - 이유: 파일 탐색, 문서 파싱, DB 변수, 실패 메시지를 바로 구현 가능한 수준으로 확정하기 쉽다.
2. 실제 규칙 구현 전 `ecm_list` 운영 DB에 `WD` 컬럼을 추가하는 흐름을 정한다.
   - 추천: `sync_sheets.py`와 샘플 `ecmlist.db`, `ecmlist2.db` 스키마를 함께 맞춘다.
   - 이유: 시험계획서 규칙의 `{WD}-3` 검사가 해당 값을 직접 필요로 한다.
3. 1~7번 중 먼저 구현할 규칙 묶음을 정한다.
   - 추천: 파일 존재/파일명 조건 중심인 1, 3, 4번부터 구현한다.
   - 이유: 파서 의존성이 적어 규칙 실행/결과 저장 골격을 빠르게 검증할 수 있다.
4. Word/Excel/PDF 파서 의존성을 점검한다.
   - 추천: `.docx`, `.xlsx`, `.pdf`를 우선 구현하고, 실제 `.xls` 샘플이 있으면 `xlrd` 의존성을 추가한다.
   - 이유: `.xls`는 `.xlsx`와 다른 reader가 필요할 수 있다.
5. 다운로드 검토 테스트가 끝나면 시간 제한을 운영 기준으로 원복한다.
   - `DOWNLOAD_REVIEW_START_HOUR = 20`
   - `DOWNLOAD_REVIEW_END_HOUR = 7`

## 결정 필요

1. 8~18번 규칙 정의가 필요하다.
   - 추천: 다음에도 3~5개씩 전달한다.
   - 이유: 애매한 조건을 바로 질문하고 확정하기 좋다.
2. `WD` 컬럼을 어떤 방식으로 `ecm_list`에 채울지 결정해야 한다.
   - 추천: Google Sheet 동기화 단계에서 `WD`까지 같이 적재한다.
   - 이유: 규칙 실행 중 별도 DB를 조인하지 않고 한 프로젝트 기준정보를 한 곳에서 읽을 수 있다.
3. 실제 구현 시작 순서를 정해야 한다.
   - 추천: 1, 3, 4번부터 구현한다.
   - 이유: 파일 존재/파일명/개수 검사만으로 규칙 엔진의 실제 결과 저장 흐름을 먼저 안정화할 수 있다.
