# GSCert Next Step

## 2026-06-24: Phase 5 로컬 exe 패키징 검증

- `local_review_app/scripts/package_windows.ps1`가 저장소 루트를 PyInstaller `--paths`에 추가해 `gscert_review_core`를 포함하도록 수정했다.
- 공용 엔진과 문서 파서 누락을 막기 위해 `gscert_review_core` submodule collect와 `fitz`, `lxml.etree`, `openpyxl`, `xlrd`, `xlrd.compdoc` hidden import를 추가했다.
- `local_review_app/run.py --self-check`를 추가해 GUI를 띄우지 않고 공용 엔진, lxml, xlrd, PyMuPDF, openpyxl import와 최소 엔진 호출을 검증한다.
- 패키징 스크립트가 빌드 직후 `GSCertLocalReview.exe --self-check`를 실행해 배포 exe의 실행 가능 상태를 자동 확인한다.
- Python 3.13 venv에서 `.\scripts\package_windows.ps1` 실행을 완료했고, `local_review_app/dist/GSCertLocalReview/GSCertLocalReview.exe` 생성 및 self-check 통과를 확인했다.

## 2026-06-24: Phase 4 로컬 runner 공용 엔진 전환

- `local_review_app/gscert_local_review/local_runner.py`를 자체 로컬 규칙 구현에서 `gscert_review_core.engine.evaluate_rules`를 호출하는 thin-adapter로 전환했다.
- 로컬 스캔 파일은 `engine.FileInfo`, 서버 rule bundle은 `RuleSpec`, 프로젝트 기준정보는 `engine.build_context(...)`로 변환해 웹과 Windows 앱이 같은 점검 엔진을 사용한다.
- Windows 앱에서 조회/선택한 `ProjectMetadata`를 `run_cached_rules(..., metadata=...)`로 넘기도록 연결해 회사명, 제품명, 시험기간, 인증일 기준값을 로컬 점검에서도 사용할 수 있게 했다.
- 코어 타입에 `target_file_pattern`을 추가해 서버 rule bundle 필드와 공용 엔진의 파일 매칭 로직을 맞췄다.
- 로컬 앱 의존성에 `lxml`, `xlrd`를 추가했다. 이후 Phase 5에서 exe 패키징 포함 검증까지 완료했다.

## 2026-06-19: 점검 결과 엑셀 다운로드 UI/API

- `/download-review/` 점검 결과 상세 팝업 크기를 기존 대비 약 1.2배로 확대했다.
- 프로젝트별 상세 팝업 안에 `엑셀 다운로드` 버튼을 추가하고, `GET /api/job-projects/<job_project_id>/results.xlsx`로 현재 팝업 내용을 다운로드하도록 연결했다.
- 작업 조회 탭의 프로젝트 목록 상단에 `전체 엑셀 다운로드` 버튼을 추가하고, `GET /api/jobs/<job_id>/results.xlsx`로 선택 작업의 전체 프로젝트/규칙 결과를 한 번에 다운로드하도록 연결했다.
- 진행 상황 탭의 상세 버튼에서 사용하던 규칙 결과 팝업 함수가 누락된 상태였으므로, 동일 API와 엑셀 다운로드 버튼을 사용하는 팝업 흐름으로 보완했다.
- 관련 Excel 응답 테스트는 `main.tests.DownloadReviewJobsApiTests.test_result_excel_endpoints_return_workbooks`에 추가했다.

## 2026-06-19: 점검규칙 DB 수정 빠른 가이드

- 점검규칙 저장 DB/테이블/컬럼과 실무 수정 예시는 `main/docs/27_rule_db_edit_quick_guide.md`에 정리했다.
- 규칙 수정이 필요하면 먼저 해당 문서에서 `inspection_rule.config_json` 예시와 seed 반영 절차를 확인한다.

## 2026-06-19: Windows 로컬 규칙 실행기 1차 연결

- Windows 앱이 서버에서 받은 규칙 bundle 캐시를 읽어 로컬 폴더 스캔 결과와 비교하도록 `local_review_app/gscert_local_review/local_runner.py`를 추가했다.
- 앱 화면에 `점검 실행` 버튼과 규칙별 결과 테이블을 추가했다.
- 현재 로컬에서 직접 판단하는 규칙 유형은 `required_artifact_file`, `required_file_name_contains`, `downloadable_artifact_check`, `rawdata_folder_structure_check`이다.
- `document_artifact_check`는 필요한 파일 개수와 Word/PDF 기본 내용 검사 일부를 로컬에서 판단한다.
- `.xlsx` 문서는 시트명/제목 같은 기초 조건을 확인한다.
- 복잡한 산출물 간 비교가 필요한 규칙은 이후 Phase 4에서 공용 엔진 위임으로 전환했다.
- 다음 단계는 로컬 exe 패키징에 공용 엔진과 문서 파서 의존성을 안정적으로 포함하는 것이다.

## 2026-06-18: PostgreSQL/API 및 Windows 앱 테스트 매뉴얼

- PostgreSQL/API 조회 매뉴얼은 `main/docs/24_postgresql_api_access_manual.md`에 정리했다.
- Windows 로컬 앱 테스트 매뉴얼은 `main/docs/25_local_windows_app_test_manual.md`에 정리했다.
- 현재 외부 PC에서 PostgreSQL에 직접 접속하는 구조는 아니며, 외부 조회는 Django API를 통해 수행하는 것으로 정리했다.
- `SELECT` 쿼리를 API 호출로 대체하는 방식과 SQL/API 매핑 예시는 `24_postgresql_api_access_manual.md`에 추가했다.
- 현재 Windows 앱은 폴더 선택, 프로젝트번호 추정, 서버 기준정보 조회, 로컬 파일 스캔, 공용 점검 엔진 실행, exe 패키징 self-check까지 테스트할 수 있다.

## 2026-06-19: 점검규칙 공유 아키텍처

- 현재 점검규칙 저장/실행 구조와 웹/Windows 앱 공유 목표 구조는 `main/docs/26_rulebase_shared_architecture.md`에 구성도로 정리했다.
- 현재 웹과 Windows 앱은 `inspection_rule` DB의 규칙 bundle과 `gscert_review_core.engine` 공용 실행 코드를 함께 사용한다.
- 권장 구조는 중앙 rulebase DB + 규칙 배포 API + 공용 점검 엔진이며, Windows 앱은 규칙 정의 업데이트와 프로그램 업데이트를 분리해서 적용한다.
- 1차 구현으로 `GET /api/local-review/rules/manifest/`, `GET /api/local-review/rules/bundle/` API를 추가하고 Windows 앱에서 규칙 버전 확인/다운로드/로컬 캐시 저장까지 연결했다.

## 2026-06-17: 로컬 Windows 점검 앱 및 PostgreSQL 전환

- 결정사항과 전환 설계는 `main/docs/23_local_desktop_postgresql_design.md`에 정리했다.
- 권장 구조는 Windows `.exe` 앱이 로컬 파일 점검을 수행하고, 프로젝트 기준정보는 Django API를 통해 서버 PostgreSQL에서 조회하는 방식이다.
- PostgreSQL DB 이름은 `gscert_prod`, 앱 계정은 `gscert_app`으로 진행한다.
- 데스크톱 앱은 DB에 직접 접속하지 않고 API만 호출한다.
- 서버용 PostgreSQL settings 모듈은 `myproject/postgres_settings.py`로 추가했다.
- 로컬 앱 배포 폴더는 `local_review_app/`로 분리했다.
- 서버 API는 `GET /api/local-review/health/`, `GET /api/local-review/projects/<project_number>/metadata/`를 추가했다.
- 로컬 앱 1차 구현은 폴더 선택, 프로젝트번호 추정, 서버 기준정보 조회, 로컬 파일 스캔, PyInstaller 패키징 스크립트까지 포함한다.
- 이후 구현 순서는 패키징된 Windows 앱으로 실제 ECM 제출물 폴더를 점검해 웹 결과와 비교하고, 필요하면 PostgreSQL 운영 전환 절차를 별도 검증하는 것이다.

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
- rawdata zip만 다운로드된 경우에도 rawdata 전용 규칙은 계속 검사한다. 일부 zip이 깨져도 읽을 수 있는 다른 zip의 규칙 검사는 계속 진행하며, `raw_data.zip`/`raw-data.zip`/중첩 zip도 rawdata로 인식한다.
- 결함리포트 보고일자는 프로젝트번호, 시트명, 보고일자 셀이 분리된 양식도 정상으로 인정한다. 날짜가 맞는데도 `보고일자` 표시 문구 차이처럼 보이며 부적합 처리되는 문제를 보정했다.
- 결함차수 산출이 실패해도 최종 결함리포트에서 `{잔여결함수}`를 먼저 산출해 테스트케이스 잔여 F 개수 비교에 사용한다. 결함리포트 `시험환경 :` 라벨의 오른쪽 셀 값도 함께 비교한다.
- 시험환경구성도는 `{프로젝트번호}`와 `구성도`가 포함된 `.png` 또는 `.pptx`가 1개 이상 있으면 통과한다. rawdata의 `성능` 폴더는 하위 폴더나 파일이 하나라도 있으면 통과하고, 완전히 비어 있을 때만 실패한다.

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
python -m py_compile local_review_app\gscert_local_review\local_runner.py local_review_app\gscert_local_review\app.py gscert_review_core\types.py local_review_app\tests\test_project.py
$env:PYTHONPATH='D:\ECM_Review\local_review_app'; python -m unittest discover local_review_app\tests
cd local_review_app
.\scripts\package_windows.ps1
git diff --check
```

예상/최근 결과:

- Django test: 49개 통과
- seed dry-run: `created=0 updated=10 unchanged=8`
- 로컬 앱 unittest: 9개 통과
- 로컬 앱 PyInstaller 빌드 및 exe self-check: 통과
- `git diff --check`: whitespace 오류 없음

## 실제 사용 시 주의점

- 바닥글 양식번호 금지어는 `TIS-`로 확정했다.
- Word/Excel 머리글/바닥글이 이미지나 필드 코드로만 들어간 경우 텍스트 추출이 되지 않아 실패할 수 있다. 운영 템플릿은 텍스트 머리글/바닥글을 유지하는 것이 좋다.
- Excel 숨김 시트도 현재 파서 기준으로 검사 대상이다.
- zip 내부 파일의 실제 생성일은 안정적으로 보존되지 않으므로 제품 스크린샷 날짜 검사는 zip entry 수정일자를 기준으로 한다.
- `test.zip`의 남은 실패는 현재 기준으로 코드 문제가 아니라 테스트 문서/파일 수정 대상으로 본다.

## 바로 다음 작업

1. 패키징된 `GSCertLocalReview.exe`로 실제 ECM 제출물 폴더를 선택해 웹과 같은 규칙 결과가 나오는지 비교한다.
2. 실제 PC 배포 절차를 정리한다. 현재 배포 대상은 `local_review_app/dist/GSCertLocalReview/` 폴더 전체다.
3. `test.zip`의 남은 9개 실패 항목은 실제 산출물 수정 후 `/download-review/` 또는 직접 검사 스크립트로 18개 전체 통과 여부를 확인한다.

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
