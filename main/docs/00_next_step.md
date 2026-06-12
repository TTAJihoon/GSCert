# GSCert Next Step

이 문서는 누적 이력 문서가 아니라 다른 PC에서 바로 이어받기 위한 최신 인수인계 문서다. 전체 목차는 `main/docs/18_manual_index.md`를 먼저 본다.

## 현재 기준

- 작업 브랜치: `codex-job-runner-persistence`
- 로컬 브랜치는 `origin/codex-job-runner-persistence`보다 앞서 있으며, 현재 작업 변경은 아직 커밋하지 않았다.
- 현재 로컬에 `test.zip`이 추적되지 않은 샘플 파일로 남아 있다. 검증 샘플이므로 Git에는 올리지 않는다.
- 다운로드 검토 페이지: `http://127.0.0.1:8000/download-review/`
- 서버 실행 예시: `.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- 테스트용 작업 시작 가능 시간: 현재 `00:00-24:00`
- 운영 복원 기준 시간: `20:00-07:00`
- 운영 복원 마커: `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`

## 다른 개발 PC에서 시작

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

Codex skill을 설치하려면:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force `
  ".\main\docs\codex_skills\gscert-download-review-maintainer" `
  "$env:USERPROFILE\.codex\skills\gscert-download-review-maintainer"
```

## 먼저 읽을 문서

1. `main/docs/18_manual_index.md`
2. `main/docs/19_inspection_rule_manual.md`
3. `main/docs/20_download_review_operations_manual.md`
4. `main/docs/21_developer_change_manual.md`
5. `main/docs/15_open_decisions.md`

## 최근 완료 작업

- 2, 7, 9, 10, 11번 규칙에 머리글/바닥글 조건을 추가했다.
  - 2번 합의서: Word 머리글 `{프로젝트번호}` 포함, Word 바닥글 `TIS-0101-3 (00)` 포함.
  - 7번 시험계획서: Word 바닥글 `TIS-`, `소프트웨어시험인증연구소` 금지.
  - 9번 테스트케이스: Excel 바닥글 `소프트웨어시험인증연구소` 금지.
  - 10번 결함리포트: 모든 Excel 시트 머리글 `프로젝트번호` 금지, 바닥글 `소프트웨어시험인증연구소` 금지.
  - 11번 점검표: 모든 Excel 시트 바닥글 `TIS-` 금지, `한국정보통신기술협회` 필수.
- Word `header*.xml` 추출과 Excel `footer_text` 추출을 구현했다.
  - `.xlsx`: odd/even/first footer 전체를 검사한다.
  - `.xls`: BIFF FOOTER(0x15) 레코드를 직접 파싱한다.
- 정상 샘플 테스트 데이터와 회귀 테스트를 새 조건에 맞춰 보강했다.
- 로컬 `workflow.db` 실제 규칙 seed도 `--only-real --enable --update-existing`로 갱신했다.
- 기준 규칙 문서 `main/docs/19_inspection_rule_manual.md`와 Codex skill rules reference를 갱신했다.

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_download_review_inspection.py main\management\commands\seed_download_review_rules.py main\tests.py
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

결과:

- Django test: 36개 통과
- seed dry-run: `created=0 updated=0 unchanged=18`
- `git diff --check`: whitespace 오류 없음

## 실제 사용 시 주의점

- 바닥글 양식번호 금지어는 `TIS-`로 확정했다. `TIS` 일반 문자열보다 오탐 가능성이 낮다.
- Word 머리글/바닥글이 이미지나 필드 코드로만 들어간 경우 텍스트 추출이 되지 않아 실패할 수 있다. 운영 템플릿은 텍스트 머리글/바닥글을 유지하는 것이 좋다.
- Excel 숨김 시트도 현재 파서 기준으로 검사 대상이다. 숨김 템플릿 시트를 남기는 파일은 머리글/바닥글 조건에서 실패할 수 있다.
- `.xls` BIFF footer 파싱은 구조가 심하게 손상된 파일에서는 빈 값으로 읽힐 수 있다. 이런 경우 필수어 검사는 실패하고 금지어 검사는 통과한다.

## 바로 다음 작업

1. 실제 테스트용 프로젝트 1건을 정한다. 모든 산출물이 들어 있는 정상 zip이 가장 좋다.
2. `main/data/ecmlist.db` 또는 `ecmlist2.db`에 해당 프로젝트 행과 기준값이 있는지 확인한다.
3. 서버와 worker를 실행하고 `/download-review/`에서 해당 프로젝트를 예약한다.
4. 작업 완료 후 작업 조회/규칙 상세 팝업에서 실패 규칙과 산출물 버튼을 확인한다.
5. 실제 테스트가 끝나면 download-review 시작 가능 시간을 운영 기준 `20:00-07:00`으로 복구한다.

## 결정 필요

1. 실제 테스트에 사용할 프로젝트 번호와 센터를 정해야 한다.
   - 추천: 최근 산출물 구성이 가장 완전한 프로젝트 1건을 먼저 사용한다. 규칙 실패가 실제 오류인지 cascade인지 구분하기 쉽다.
2. 실제 테스트가 끝난 뒤 테스트용 전체 시간 허용을 언제 운영 시간으로 되돌릴지 정해야 한다.
   - 추천: 정상 산출물 zip 검증과 UI 확인이 끝난 즉시 `20:00-07:00`으로 복구한다.
