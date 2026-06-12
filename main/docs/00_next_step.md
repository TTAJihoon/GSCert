# GSCert Next Step

이 문서는 누적 이력 문서가 아니라 다른 PC에서 바로 이어받기 위한 최신 인수인계 문서다. 전체 목차는 `main/docs/18_manual_index.md`를 먼저 본다.

## 현재 기준

- 브랜치: `codex-job-runner-persistence`
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

점검규칙과 산출물 조회 기반을 확장했다.

- 구현된 실제 규칙: 1~13번, 15~18번
- 새 rule_type:
  - `excel_feature_list_check`
  - `test_plan_document_check`
  - `image_screenshot_folder_date_check`
  - `test_case_check`
  - `defect_report_check`
  - `inspection_checklist_check`
  - `quality_inspection_table_check`
  - `quality_evaluation_report_check`
  - `rawdata_folder_structure_check`
  - `test_report_document_check`
- artifact 저장소/API:
  - 저장 위치: `main/data/download_review_artifacts/`
  - 조회 API: `GET /api/rule-results/{result_id}/artifacts/{artifact_id}/`
  - UI 규칙 결과 모달에 `산출물` 열을 추가했다.
  - 서버 절대경로는 API/UI에 노출하지 않는다.
- 2번 합의서:
  - `.pdf` 1페이지를 PNG로 저장하고 UI에서 버튼으로 조회할 수 있다.
- 6번 기능리스트:
  - `대분류` 기준 Excel 영역을 표 이미지로 렌더링해 UI에서 버튼으로 조회할 수 있다.
- 13번 시험성적서:
  - `시험 > 종료` 폴더에서 `시험성적서`와 `{프로젝트번호}`를 포함한 `.docx` 1개, `.pdf` 1개를 검사한다.
  - `.docx`의 `결함리포트 송부` 표에서 `{1차}`, `{2차}`, 선택적 `{3차}`, `{4차}` 날짜와 `{결함차수}`를 산출한다.
  - `<세부사양>` 다음 표를 `raw_detail_json.spec_table`과 `{시험성적서_세부사양표}` 변수에 저장한다.
  - `.pdf` 1페이지를 PNG로 저장하고 UI에서 버튼으로 조회할 수 있다.
- 7번 시험계획서:
  - `시험 > 계획` 폴더에서 `계획서`와 `{프로젝트번호}`를 포함한 `.docx` 1개, `.pdf` 1개를 검사한다.
  - 첫 번째 표의 시작일/담당자/PL, 두 번째 표의 제품명/버전/시험신청번호를 검사한다.
  - `5.1 형상항목 식별 규칙` 다음 표의 `형상항목 ID`, `2.2 시험일정` 다음 표의 `WD` 값을 검사한다.
  - 바닥글의 `Copyright {연도} TTA`를 정확히 검사한다.
  - 13번 시험성적서가 산출한 `{시험성적서_세부사양표}`와 `<세부사양>` 다음 표를 정규화 후 완전 일치 비교한다.
  - PDF 1페이지를 산출물로 저장한다.
- 규칙 산출 변수:
  - 규칙이 `raw_detail_json.variables`에 저장한 값은 같은 실행의 후속 규칙에서 `{변수명}`으로 참조할 수 있다.
  - 저장된 결과 기준 변수 조회 helper도 추가했다.
  - 13번 시험성적서가 10번 결함리포트보다 먼저 실행되도록 실제 규칙 seed `sort_order`를 조정했다.
- 10번 결함리포트:
  - 13번 시험성적서에서 산출한 `{결함차수}`, `{1차}`, `{2차}` 등을 읽어 결함리포트 Excel 파일을 검사한다.
  - 결함리포트 파일 수가 `{결함차수}+1`보다 많거나 적으면 `시험성적서의 결함 차수와 결함리포트 개수가 다름`으로 실패 처리한다.
  - 버전별 누적 시트 구성, 시험환경 동일성, 보고일자, 마지막 버전의 `{잔여결함수}`, `{H}`, `{R}` 산출을 구현했다.
- 9번 테스트케이스:
  - `설계` 폴더 아래 `{프로젝트번호}`와 `테스트케이스`를 포함한 Excel 1개를 검사한다.
  - 시트 1개, `{프로젝트번호} 테스트케이스`, `작성자: {PL}`, 바로 아래 `검토자: 김진영`, `작성일: {시작일} ~ {종료일}`을 검사한다.
  - 10번 결함리포트에서 산출한 `{잔여결함수}`를 읽어 `상세 테스트 결과` 열의 `F` 개수와 비교한다.
  - seed `sort_order=105`로 10번 결함리포트 뒤에 실행되도록 했다.
- 11번 점검표:
  - `설계` 폴더 아래 점검표 Excel 1개와 PDF 정확히 1개를 검사한다.
  - 모든 시트 머리글, 표지 제목/날짜/작성자, 기능별 점검표 빈 셀, 기능적합성 표 비교, 신뢰성 WD/H/R 값을 검사한다.
  - PDF 1페이지를 산출물로 저장하고 `{측정항목별점수표}`를 산출한다.
- 16번 품질검사표:
  - `시험 > 인증관련` 폴더 아래 품질검사표 Excel 1개를 검사한다.
  - `{프로젝트번호} 품질검사표` 단일 시트인지 확인한다.
  - 11번 점검표가 산출한 `{측정항목별점수표}`와 D4~D87 값을 비교한다.
  - E4~E85 실제 값 33개를 `4~33, 1~3` 순서로 재정렬해 `{품질부특성측정값}`을 산출한다.
- 15번 품질평가보고서:
  - `시험 > 인증관련` 폴더 아래 품질평가보고서 docx 1개를 검사한다.
  - 프로젝트번호 6회, 서명란 이름, 회사명, 신청일/계약일/시험기간/인증위 날짜를 검사한다.
  - 16번 품질검사표가 산출한 `{품질부특성측정값}`과 `<품질특성별 세부 평가결과>` 표를 비교한다.
  - `NA`/`N/A` 값 오른쪽 칸에 `해당사항 없음`이 있는지 검사한다.
- Google Sheet H/I열을 `신청일`/`계약일`로 `ecmlist.db`와 `ecmlist2.db`에 저장하도록 보강했다.
- `requirements.txt`에 `.xls` 파싱용 `xlrd>=2.0,<2.1`을 추가했다.

## 검증 완료

다음 명령을 실행해 검증했다.

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

## 바로 다음 작업

1. 14번 시험기록서를 구현한다.
   - `시험 > 종료` 폴더에서 `시험기록서`와 `{프로젝트번호}`를 포함한 PDF 1개를 찾는다.
   - 사용자가 직접 확인할 수 있도록 다운로드형 산출물 버튼으로 제공한다.
2. 14번 구현 후 실제 규칙 1~18번 중 14번을 제외한 빈틈이 없는지 seed와 통합 테스트를 다시 확인한다.
3. 실제 샘플 zip 또는 live 다운로드 결과로 전체 규칙 순서를 검증한다.

## 결정 필요

1. 14번 시험기록서 PDF 제공 방식 확정이 필요하다.
   - 추천: 검사 결과는 파일 존재 여부만 자동 판정하고, 산출물 버튼은 `download=true`로 제공해 브라우저에서 바로 다운로드되게 한다.
