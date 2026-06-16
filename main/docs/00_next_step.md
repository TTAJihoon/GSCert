# GSCert Next Step

이 문서는 누적 이력 문서가 아니라 다른 PC에서 바로 이어받기 위한 최신 인수인계 문서다. 전체 목차는 `main/docs/18_manual_index.md`를 먼저 본다.

## 현재 기준

- 작업 브랜치: `codex-job-runner-persistence`
- 최신 작업은 이 브랜치에 커밋/푸시해서 이어받는다.
- 로컬 샘플 `test.zip`은 검증용 파일이며 Git에 올리지 않는다.
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

- `test.zip` 실제 점검을 기준으로 규칙 실행 예외와 cascade 문제를 보정했다.
- `.xls` BIFF HEADER/FOOTER 파서 버그를 수정해 점검표 머리글/바닥글을 정상 추출한다.
- 결함리포트가 바닥글 등 후속 조건에서 실패해도, 최종 버전 파일에서 `{잔여결함수}`, `{H}`, `{R}`을 찾을 수 있으면 산출 변수로 저장한다.
- 품질검사표가 점검표 D열 비교에서 실패해도 `{품질부특성측정값}`은 먼저 산출해 품질평가보고서 비교가 계속 진행되도록 했다.
- 품질검사표/품질평가보고서 값 비교는 양쪽 모두 숫자로 해석 가능하면 숫자값으로 비교한다. 예: `1`, `1.0`, `1.00`은 동일하다.
- 품질평가보고서는 `<품질특성별 세부 평가결과>` 문장이 목차에도 나타나는 문제를 피하기 위해, 문서의 마지막 표부터 역순으로 확인하여 1행 1열에 `품질특성` 단어가 포함된 표를 찾는다.
- `{품질부특성측정값}` 산출 순서는 원본 33개 중 27번째 값을 제외하고 `4~26, 28~33, 1~3`으로 확정했다.
- 제품 스크린샷 수정일자 오류 메시지는 시험기간, 범위 밖 수정일자 목록, 총 이미지 개수를 함께 표시한다.
- 기준 규칙 문서 `main/docs/19_inspection_rule_manual.md`를 최신 구현 기준으로 갱신했다.

## test.zip 현재 결과

최종 재점검 결과:

- 통과: 9개
- 실패: 9개

통과:

- 계약서
- 합의서(PDF)
- 수수료산정표
- 시험환경구성도
- 기능리스트
- 시험성적서(PDF)
- 점검표(PDF)
- 1차/2차/성능/보안RawData
- 품질평가보고서

남은 실패 분류:

- 실제 문서 내용 수정 필요
  - 품질특성별제품정보기재사항: 제목/프로젝트번호 문구 불일치
  - 시험계획서(PDF): 기대 버전 `v1.0`, 실제 `1.0`
  - 결함리포트: 바닥글 금지어 `소프트웨어시험인증연구소`
  - 테스트케이스: 바닥글 금지어 `소프트웨어시험인증연구소`
  - 품질검사표: 점검표와 비교 시 총 84개 중 11개 값 다름
- 파일 누락
  - 시험기록서 PDF 없음
  - SW저작권확인서 PDF 없음
  - 홍보이미지 없음
- 메타데이터/날짜 문제
  - 최초/최종형상RawData: `시험기간은 2026.04.17.~2026.05.14.인데 수정일자가 2026.04.16.인 이미지가 28개 존재함`

## 검증 완료

```powershell
.\.venv\Scripts\python.exe -m py_compile main\views\review\ecm_download_review_inspection.py main\management\commands\seed_download_review_rules.py main\tests.py
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

예상/최근 결과:

- Django test: 40개 통과
- seed dry-run: `created=0 updated=0 unchanged=18`
- `git diff --check`: whitespace 오류 없음

## 실제 사용 시 주의점

- 바닥글 양식번호 금지어는 `TIS-`로 확정했다.
- Word/Excel 머리글/바닥글이 이미지나 필드 코드로만 들어간 경우 텍스트 추출이 되지 않아 실패할 수 있다. 운영 템플릿은 텍스트 머리글/바닥글을 유지하는 것이 좋다.
- Excel 숨김 시트도 현재 파서 기준으로 검사 대상이다.
- zip 내부 파일의 실제 생성일은 안정적으로 보존되지 않으므로 제품 스크린샷 날짜 검사는 zip entry 수정일자를 기준으로 한다.
- `test.zip`의 남은 실패는 현재 기준으로 코드 문제가 아니라 테스트 문서/파일 수정 대상으로 본다.

## 바로 다음 작업

1. `test.zip`의 남은 9개 실패 항목을 실제 산출물에서 수정한다.
2. 수정한 zip으로 `/download-review/` 또는 직접 검사 스크립트를 다시 실행해 18개 전체 통과 여부를 확인한다.
3. 실제 테스트가 끝나면 download-review 시작 가능 시간을 운영 기준 `20:00-07:00`으로 복구한다.

## 결정 필요

1. 남은 9개 실패를 규칙 완화 없이 문서/파일 수정으로 처리할지 유지 결정한다.
   - 추천: 규칙은 유지한다. 현재 실패 항목은 앞서 확정한 규칙과 직접 연결되어 있어 완화하면 검증력이 떨어진다.
2. `test.zip` 수정 후 전체 통과 기준을 언제 운영 시간 복구 시점으로 볼지 정한다.
   - 추천: 샘플 zip 18개 전체 통과와 UI 결과 확인이 끝난 직후 `20:00-07:00`으로 복구한다.

## 2026-06-16 추가 반영

- 기대값 표시 매핑 문서는 `main/docs/22_expected_value_display_mapping.md`에 EV-001~EV-134 고정 번호로 정리했다.
- 합의서, 시험계획서, 시험성적서, 품질평가보고서, 적합평가보고서의 Word 파일 범위는 `.docx`에서 `.docx`, `.docm`으로 확대했다.
- 품질특성별 제품 정보 기재사항 제목 점검은 긴 고정 제목 대신 `{project_number}`와 `품질특성별` 문구가 함께 있는지 확인한다.
- 평가표 EV-100의 기능별 점검표 B~D와 기능적합성 A~C 비교 규칙은 제외했다.
- 결함리포트에서 산출하는 H값은 `시험분석자료` 시트에서 E열 값이 `H`이고 C열 값이 `-` 또는 공백이 아닌 행 개수로 산정한다.
