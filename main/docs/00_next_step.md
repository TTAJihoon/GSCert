# GSCert Next Step

이 문서는 누적 이력 문서가 아니라 다른 PC에서 바로 이어받기 위한 최신 인수인계 문서다. 전체 목차는 `main/docs/18_manual_index.md`를 먼저 본다.

## 현재 기준

- 작업 브랜치: `codex-job-runner-persistence`
- `download-review-inspection-fixes`의 14번 시험기록서 구현과 `test.zip` 검증 수정분을 병합했다.
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

- ECM 보고서 탐색과 다운로드 검토 UI의 resizable column 변경을 유지했다.
- `test.zip` 샘플 검증으로 찾은 검사 엔진 버그를 수정했다.
  - Word 본문/머리말/바닥글의 `w:t` run 분리 때문에 날짜와 프로젝트번호가 깨지던 문제를 수정했다.
  - `.xls` 인쇄 머리글을 BIFF HEADER 레코드에서 직접 읽어 11번 점검표 머리글 검사를 보강했다.
  - Excel 정수 `0` 값이 빈 문자열로 처리되던 문제를 수정했다.
  - 회사명/제품명에 줄바꿈이 있는 경우 첫 줄만 기준값으로 사용하도록 보정했다.
- 1~18번 전체 실제 점검규칙이 구현되어 `--only-real` seed 기준 활성화 가능하다.
- 14번 시험기록서를 구현했다.
  - `시험 > 종료` 폴더에서 `시험기록서`와 `{프로젝트번호}`를 포함한 PDF 1개를 찾는다.
  - 내용 자동 검사는 하지 않고, 원본 PDF를 `download=true` 산출물로 제공한다.
- 주요 산출물 API/UI 흐름:
  - 저장 위치: `main/data/download_review_artifacts/`
  - 조회 API: `GET /api/rule-results/{result_id}/artifacts/{artifact_id}/`
  - 서버 절대경로는 API/UI에 노출하지 않는다.
- 주요 실행 순서:
  - 13번 시험성적서: `sort_order=95`
  - 7번 시험계획서: `sort_order=96`
  - 10번 결함리포트: `sort_order=100`
  - 9번 테스트케이스: `sort_order=105`
  - 11번 점검표: `sort_order=110`
  - 14번 시험기록서: `sort_order=140`
  - 16번 품질검사표: `sort_order=145`
  - 15번 품질평가보고서: `sort_order=150`
- `test.zip` 실행 시 PASS 7/18이며, 남은 FAIL은 샘플 자체의 의도된 오류와 cascade로 설명된다.
  - 의도된 샘플 오류: 5, 17, 18
  - 현행 엄격 유지 결정: 7 버전, 10 시험환경
  - 10번 실패 cascade: 9, 11, 16, 15
  - 14번 파일 없음

## 검증 명령

병합 후 아래 명령을 실행한다.

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

## 바로 다음 작업

1. 전체 검증을 재실행한다.
2. 검증 통과 후 merge commit을 완료하고 `codex-job-runner-persistence`를 push한다.
3. 실제 정상 산출물 zip으로 전체 규칙이 PASS 18/18 되는지 확인한다. 현재 `test.zip`은 의도된 오류가 섞인 샘플이라 PASS 7/18이 정상이다.
4. UI 변경 확인이 필요하면 서버를 재시작하고 `/download-review/`에서 resizable column과 산출물 버튼을 확인한다.
5. 테스트가 끝나면 download-review 시작 가능 시간을 운영 기준 `20:00-07:00`으로 복구한다.

## 결정 필요

1. 정상 산출물 zip 검증 대상을 정해야 한다.
   - 추천: 최근 실제로 검토가 완료된 프로젝트 1건을 사용한다. 모든 산출물이 들어 있어 18개 규칙의 cascade 없이 확인하기 좋다.
2. 테스트용 전체 시간 허용을 언제 운영 시간으로 되돌릴지 정해야 한다.
   - 추천: 정상 산출물 zip과 UI 확인이 끝난 직후 `20:00-07:00`으로 복구한다.

## 검증 하니스 메모

워커는 ECM 브라우저 자동화에 묶여 있어 zip 단독 검사 진입점이 없다. `test.zip`으로 전체 규칙을 검증하려면 `_build_rule_context`와 `_evaluate_rule` 루프를 `SimpleNamespace` project + `DownloadVerifyResult(files=[FileInfo(test.zip)])`로 직접 호출하는 일회성 스크립트를 쓴다. `_inspection_files`가 최상위 zip을 자동 확장한다. 사전조건은 `ecmlist.db`에 해당 프로젝트번호 행이 존재하는 것이다.
