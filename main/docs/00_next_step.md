# GSCert Next Step

## 2026-07-07: ECM 다운로드 HTTP 직접연동 — 코드 착수 완료 (실서버 실측만 남음)

- **완료:** ECM 산출물 다운로드의 **서버측 HTTP 직접 호출(`requests`)** 방식(`ecm-http` source)을
  구현했다. 결정 1~12(`main/docs/34_http_ecm_source_decisions.md`)를 코드로 옮겼고 단위 테스트를 통과했다.
  **아직 남은 것은 실서버(사용자 PC) 실측뿐**(결정 12b: 샌드박스는 210.x 접속 불가).
- **설계대로 어댑터만 추가:** `ArtifactSource` 심(seam) 위쪽(워커·검증·점검·상태전이)은 불변이고,
  `HttpEcmArtifactSource` 어댑터 하나를 추가했다. 문제 시 `--source=ecm`(Playwright) 즉시 롤백.
- **추가/변경 파일:**
  - 신규 `main/views/review/ecm_http_client.py` — `DestinyECM`(로그인·폴더/파일 조회·다운로드·프로젝트
    자동 탐색) 이식 + 세션만료 1회 재로그인, `build_client(center)` 팩토리.
  - `main/views/review/artifact_source.py` — `HttpEcmArtifactSource`(lazy 로그인/센터별 세션 재사용,
    재귀 순회 → `base/<NFC 프로젝트번호>/<NFC 상대경로>/`에 다운로드 + 무결성 검증 + 1회 재시도, 락 없음),
    `verify_downloaded_bytes()`, 팩토리 `ecm-http` 분기.
  - `ecm_download_review_centers.py` — 센터 dict 에 `root_oid`·계정 설정 키 + `ecm_root_oid()`/`ecm_credentials()`.
  - `settings.py`/`ui_mock_settings.py`/`env.ps1.example` — `ECM_USERNAME[_BUNDANG]`/`ECM_PASSWORD[_BUNDANG]`·
    `ECM_ROOT_OID_*`·`ECM_BASE_URL_BUNDANG`, `DOWNLOAD_REVIEW_SOURCE` 주석에 `ecm-http` 추가.
  - `requirements-automation.txt` — `requests` 추가.
  - 신규 검증 명령 `main/management/commands/verify_ecm_http.py`(결정 12b, 사용자 PC 실행용).
  - 테스트 `main/tests.py` — `HttpEcmArtifactSourceTests`, `EcmHttpClientPureFunctionTests`.
- **실서버에서 할 일(사용자 PC):**
  1. 환경변수 설정(`env.ps1` 에 `ECM_USERNAME`/`ECM_PASSWORD`[`_BUNDANG`]).
  2. `python manage.py verify_ecm_http --center <센터> --test-no <시험번호> [--date ...]` 로 로그인·탐색 확인,
     `--download --limit 3` 으로 무결성까지 확인.
  3. 통과하면 워커를 `run_download_worker --live --source=ecm-http` 로 시범 운영, 안정화 후
     `DOWNLOAD_REVIEW_SOURCE` 기본값을 `ecm-http` 로 전환(결정 11).
- **참고 자료:** 원본 구현 가이드 `ECM-API-SHARE.md`는 저장소 밖(공유). 핵심 계약은
  `34_http_ecm_source_decisions.md`에 요약돼 있고, 코드도 그 요약 기준으로 이식했다.
- **weekly.py(인증획득제품 목록 주간 동기화)도 HTTP 전환:** `main/utils/weekly.py`의 다운로드 단계를
  브라우저 SSO + Playwright + pywinauto '폴더 찾아보기' 팝업 방식에서 **`DestinyECM` HTTP 직접연동**으로 바꿨다.
  - XOR 로그인이 SSO(`edm_storage_state.json`)를 대체한다(분당 서버, `ECM_USERNAME_BUNDANG`/`ECM_PASSWORD_BUNDANG`).
  - **월요일 날짜로 문서를 지목하던 방식 → 00 폴더 파일 중 이름의 `(YYYYMMDD)`가 가장 최근인 xlsx 자동 선택**
    (올해 폴더 비면 전년도 폴백). `select_latest_list_file()`.
  - `servlet/blob` 바이트를 받아 PK(zip) 검증 후 저장 → 저장 위치 지정 팝업/pywinauto/headful 브라우저 소멸.
  - `GSCERT_WEEKLY_SOURCE=http`(기본) / `playwright`(레거시 폴백) 토글. playwright·pywinauto import는 lazy 로
    바꿔 HTTP 실행 시 두 패키지가 없어도 동작한다. 이후(행 추출→master append→PostgreSQL 적재)는 불변.
  - 테스트 `main/tests.py` `WeeklyHttpDownloadTests`(최근 날짜 선택/전년 폴백/미탐색, 네트워크 없음).
  - **실서버 확인 필요:** 분당 계정이 `인증획득제품` 00 폴더에 접근되는지 + `--limit` 없이 실제 다운로드 1회.
- **시험 이력 '문서 다운로드'(테스팅 에이전트)도 HTTP 전환:** `playwright_job`의 document 액션을
  Playwright + pywinauto('폴더 찾아보기' 팝업)에서 **HTTP 직접연동**으로 교체.
  - 트리: `{year} 시험서비스 → GS인증심의위원회 → (회차) → 인증일자(yyyymmdd) → 시험번호`.
    `DestinyECM.find_committee_test_folder()`(인증일자 폴더가 회차 폴더 밑이면 한 단계 더 탐색).
  - **기본은 시험성적서 Word 파일만** 다운로드(UI 안내문의 원래 의도와 일치. 기존 코드는 전체를 받았음).
    `select_report_documents(report_only=True)` = 이름에 `시험성적서` + `.doc/.docx/.docm`. 전체도 옵션.
  - `main/views/testing/history_download.py` 신규(login→locate→필터→report 폴더 정리→다운로드+무결성+`.scope` 마커).
    `playwright_job/consumers.py` document 액션이 이 함수를 호출(브라우저/pywinauto/에이전트 락 제거).
  - 프런트: `history.html`에 `시험성적서`/`전체 문서` 버튼(`data-scope`), `history_document.js`가 `scope` 전달.
    `.scope` 마커로 범위별 캐시 구분(같은 범위면 ECM 재접속 없이 report ZIP 재사용).
  - 인증위원회는 분당 ECM(210.104.181.10)이라 `center=bundang`. 자격증명은 `ECM_USERNAME_BUNDANG` 등.
  - 검증: `manage.py verify_ecm_http --history --center bundang --test-no GS-B-22-355 --date 2022-08-15 [--download] [--all]`.
    테스트 `HistoryDocumentHttpTests`(트리 탐색/성적서 필터/캐시 마커, 네트워크 없음).
  - **실측 통과(2026-07-07):** `GS-B-23-067`(2023.07.24) → 폴더 `바. GS-B-23-067`, 시험성적서 Word 1개 다운로드 OK.
  - **두 버튼 분리:**
    - `문서 다운로드`(scope=report, 기본): 위 그대로 — 분당 인증위원회 트리의 **시험성적서 Word**.
    - `전체 다운로드`(scope=all): **프로젝트가 속한 센터**(reference_project = 점검 센터별 PL 목록)로 접속해
      점검과 동일한 `find_project_folder`({연도} 시험서비스 → GS 포함 폴더 → 프로젝트 폴더)로 폴더를 찾고,
      그 아래 **모든 파일을 상대경로 그대로** report\\<시험번호> 에 받아 ZIP. `download_full_project_documents()`.
      센터 해석은 `_resolve_project_center()`(전 센터를 `get_projects_by_numbers` 로 훑어 첫 매치).
  - **실서버 확인 필요:** 인증일자 폴더 규칙(회차 유무), 시험성적서 Word 존재 / 전체 버튼은 상암·영남 프로젝트로도 센터 자동해석·탐색 확인.

## 2026-07-03: 점검규칙 대규모 검토 후 문서 최신화

- 1~18번 실제 점검규칙은 `seed_download_review_rules --only-real --enable --update-existing` 기준으로 모두 구현된 상태다.
- 세부 규칙의 단일 원본은 `main/docs/19_inspection_rule_manual.md`로 유지한다.
- `main/docs/19_inspection_rule_manual.md`에 `1-1`~`18-3` 형식의 세부 점검 규칙 ID 표를 추가했고, `docs/INSPECTION_RULES_TABLE.md`에는 해당 ID 범위와 화면 표시 기준을 연결했다.
- `main/docs/05_zip_inspection.md`는 과거 1~5번 초안 중심 내용을 걷어내고, 현재 18개 규칙의 설계 요약과 공통 기준만 남겼다.
- `main/docs/08_ui_api_design.md`에 Windows 로컬 앱용 rulebase API(`/api/local-review/rules/manifest/`, `/api/local-review/rules/bundle/`)와 `engine_min_version=0.2.0` 계약을 추가했다.
- 최근 규칙 변경점:
  - 시험계획서 담당자, 테스트케이스 검토자, 점검표 표지 검토자는 센터별 expected 값을 사용한다. 분당 `임우섭`, 상암 `김진영`, 영남 `이재훈`, 기본값 `김진영`.
  - 시험환경구성도는 `.png` 또는 `.pptx` 1개 이상이면 통과한다.
  - 품질특성별제품정보기재사항은 `{프로젝트번호}`와 `품질특성별` 문구, 다음 문단 날짜, 바닥글 `TPG`/`TIS` 금지를 검사한다.
  - 기능리스트, 테스트케이스, 점검표, 품질검사표는 Excel 머리글/바닥글 금지어/필수어 조건을 포함한다.
  - 시험기록서는 전체 검사 대상에서 `기록서` PDF를 찾고 1페이지 캡처 이미지를 산출물로 제공한다.
  - SW저작권확인서와 홍보이미지는 폴더 누락, 파일명 누락, 확장자 불일치, 파일명 `예시` 금지 등 실패 메시지를 세분화했다.

## 바로 다음 작업

1. `.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings`로 현재 DB 반영 차이를 확인한다.
2. `.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings`로 전체 규칙 회귀를 확인한다.
3. 패키징된 Windows 앱에서 `/api/local-review/rules/manifest/`의 `engine_min_version`과 앱 `ENGINE_VERSION` 비교가 정상 동작하는지 확인한다.
4. 실제 정상 산출물 zip/폴더로 1~18번 전체 PASS 여부를 다시 확인한다.

## 2026-06-24: 분당/상암·영남 split-server 운영 라우팅

- `/download-review/` 화면이 현재 Host를 보고 기본 센터와 원격 센터 탭 URL을 결정하도록 수정했다.
- `210.96.71.194`는 분당 담당 서버로 보고 기본 센터를 `bundang`으로 설정했다.
- `210.96.71.241`은 상암/영남 담당 서버로 보고 기본 센터를 `sangam`으로 설정했다.
- 194 서버에서 상암/영남 탭을 클릭하면 241 서버의 `/download-review/?center=sangam|yeongnam`으로 이동한다.
- 241 서버에서 분당 탭을 클릭하면 194 서버의 `/download-review/?center=bundang`으로 이동한다.
- API는 현재 서버에서 처리하지 않는 센터 요청을 400으로 거절한다.
- worker는 서버 IP 또는 `DOWNLOAD_REVIEW_WORKER_CENTERS` 환경변수를 기준으로 허용 센터 작업만 claim한다.
- 운영 확인 절차는 `main/docs/29_download_review_split_server_deployment.md`에 정리했다.

## 2026-06-24: Google Sheet 프로젝트 목록 PostgreSQL 적재 준비

- 인증위 Google Sheet를 CSV export로 읽어 `reference_project` PostgreSQL 테이블에 적재하는 `sync_reference_projects_from_sheet` 관리 명령을 추가했다.
- 센터별 PL 이름 매핑은 `reference_center_pl`에 저장하며, 전화번호는 저장하지 않는다.
- 회사명/제품명은 괄호와 괄호 안 내용을 제거한 뒤 `-` 기준 1회 분리한다.
- B열의 `yyyy년 m월 d일(요일)` 날짜 블록은 뒤에 시간이 붙어도 인식하고, 해당 날짜를 인증위 날짜로 저장한다.
- 실제 프로젝트 목록은 `reference_project` 한 테이블에 저장하고, 센터별 조회 편의를 위해 `reference_project_sangam`, `reference_project_bundang`, `reference_project_yeongnam` view를 생성한다.
- `/api/projects/`와 Windows 메타데이터 API는 `DOWNLOAD_REVIEW_PROJECT_SOURCE=postgres` 설정일 때 PostgreSQL `reference_project`를 우선 조회한다.
- `/download-review/` 센터 탭에 분당을 추가했고, 센터 정의에도 `bundang`을 추가했다.
- dry-run 결과 현재 Google Sheet에서 프로젝트 144건을 파싱했다. 제공된 PL 목록 기준 분당 33건, 상암 52건, 영남 22건, 미분류 37건이다.
- 실제 DB 적재는 PostgreSQL 서버가 현재 접속 IP `210.96.71.254`를 `pg_hba.conf`에서 허용하지 않아 차단됐다. 서버에서 접속 허용 후 `main/docs/28_reference_project_sheet_sync.md`의 명령으로 다시 실행하면 된다.

## 2026-06-24: Windows 앱 점검 실행 버튼 반응 개선

- 기존 배포 exe는 `점검 실행` 클릭 후 공용 점검 엔진을 UI 스레드에서 바로 실행해, 큰 zip을 점검하는 동안 창이 멈춘 것처럼 보일 수 있었다.
- `local_review_app/gscert_local_review/app.py`에 `ReviewWorker(QThread)`를 연결해 점검 실행을 백그라운드 스레드로 옮겼다.
- 클릭 직후 버튼 텍스트가 `점검 중…`으로 바뀌고, 완료 후 결과 테이블이 갱신되며 버튼이 다시 활성화된다.
- 버튼 글씨가 흐리거나 보이지 않는 문제를 줄이기 위해 `점검 실행` 버튼의 활성/비활성 대비를 강화하고 버튼 옆에 `대기`, `파일 스캔 필요`, `점검 실행 중`, `점검 완료` 상태 문구를 추가했다.
- 점검 중에는 폴더 선택, 기준정보 조회, 파일 스캔, 프로젝트 번호 입력, 점검 실행 버튼을 잠근다.
- 자동 확인 결과 작은 샘플과 `C:\Users\jh910\Documents\New project 2\test.zip` 모두 클릭 직후 worker가 시작되고 결과 테이블이 채워졌다.
- `local_review_app/dist/GSCertLocalReview/GSCertLocalReview.exe`를 새로 패키징했으며 `--self-check`와 GUI 실행 스모크를 통과했다.

## 2026-06-24: test.zip 서버/Windows 프로그램 재검증

- `C:\Users\jh910\Documents\New project 2\test.zip`을 임시 폴더에 단독 복사해 실제 ECM 다운로드 결과가 zip 1개인 조건으로 점검했다.
- 서버 점검 경로는 활성 규칙 18개 기준 `pass=7`, `fail=11`이며, 별도 임시파일 검사는 `pass`라 전체 저장 결과는 19개 중 `pass=8`, `fail=11`이다.
- Windows 프로그램 경로는 HTTP API에서 프로젝트 메타데이터와 규칙 bundle을 받아 같은 `test.zip`으로 실행했으며 `total=18`, `pass=7`, `fail=11`, `unsupported=0`, `error=0`이었다.
- 서버 코어 규칙 결과와 Windows 프로그램 결과의 상태 불일치는 0개다.
- 로컬 프로그램에서 PDF/Excel 산출물 캡처를 만들지 않는 `NoOpArtifactSink`의 호출 시그니처가 공용 엔진과 맞지 않아 5개 규칙이 `error`로 떨어지던 문제를 수정했다.
- `local_review_app/dist/GSCertLocalReview/GSCertLocalReview.exe`를 다시 패키징했고 `--self-check`를 통과했다.

## 2026-06-24: 서버/Windows 프로그램 실사용 스모크 확인

- 서버용 루트 `.venv`를 Python 3.13으로 구성하고 `requirements.txt` 설치 후 `manage.py check --settings=myproject.ui_mock_settings`를 통과했다.
- 로컬 검증 DB에 migration을 적용하고 실제 규칙을 seed했다. 활성 규칙은 18개이며 `seed_download_review_rules --only-real --enable --update-existing --dry-run` 결과는 `created=0 updated=0 unchanged=18`이다.
- 현재 코드 기준 runserver를 `127.0.0.1:8001`에서 띄워 `/download-review/`, `/api/local-review/health/`, `/api/local-review/rules/manifest/`, `/api/local-review/rules/bundle/` 응답을 확인했다. 규칙 bundle은 18개를 반환했다.
- Windows 앱 API client가 서버 rule bundle을 받고 `local_runner.py`로 실행했을 때 `local_unsupported_count=0`이었다. 현재 활성 규칙 기준 미지원 규칙은 없다.
- 패키징된 `GSCertLocalReview.exe --self-check`는 exit code `0`이고, GUI 시작 스모크도 성공했다.
- `C:\Users\jh910\Downloads\5. 테스트용 공개 문서.zip`을 별도 임시 폴더에서 샘플 입력으로 실행했을 때 `sample_total=18`, `sample_unsupported=0`, `sample_error=0`이었다. 해당 파일은 ECM 제출물 형식이 아니므로 18개 부적합은 정상으로 본다.
- `manage.py test main.tests --settings=myproject.ui_mock_settings`는 51개 통과했고, `run_download_worker --once --dry-run`은 시작 가능한 작업 없음 상태로 정상 종료했다.

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

- 서버 코어 규칙: 통과 7개, 실패 11개
- 서버 저장 결과: 통과 8개, 실패 11개 (`temp_file_check` 통과 포함)
- Windows 프로그램/API 경로: 통과 7개, 실패 11개, 미지원 0개, 오류 0개
- 서버/Windows 프로그램 상태 불일치: 0개

통과:

- 계약서
- 합의서(PDF)
- 수수료산정표
- 시험환경구성도
- 기능리스트
- 시험성적서(PDF)
- 1차/2차/성능/보안RawData

남은 실패 분류:

- 실제 문서 내용 수정 필요
  - 품질특성별제품정보기재사항: 제목/프로젝트번호 문구 불일치
  - 시험계획서(PDF): 날짜 작성값 불일치
  - 결함리포트: 바닥글 금지어 `소프트웨어시험인증연구소`
  - 테스트케이스: 바닥글 금지어 `소프트웨어시험인증연구소`
  - 점검표(PDF): 표지 날짜 불일치
  - 품질검사표: 점검표와 비교 시 총 84개 중 11개 값 다름
  - 품질평가보고서: 시험기간 불일치
- 파일 누락
  - 시험기록서 PDF 없음
  - SW저작권확인서 PDF 없음
  - 홍보이미지 파일명에 `예시` 포함
- 메타데이터/날짜 문제
  - 최초/최종형상RawData: 제품 스크린샷 폴더를 찾을 수 없음

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
.\dist\GSCertLocalReview\GSCertLocalReview.exe --self-check
git diff --check
```

예상/최근 결과:

- Django test: 51개 통과
- seed dry-run: `created=0 updated=0 unchanged=18`
- 로컬 앱 unittest: 9개 통과
- 로컬 앱 PyInstaller 빌드 및 exe self-check: 통과
- `test.zip` 서버/Windows 프로그램 재검증: `unsupported=0`, `error=0`, 상태 불일치 0개
- `git diff --check`: whitespace 오류 없음

## 실제 사용 시 주의점

- 바닥글 양식번호 금지어는 `TIS-`로 확정했다.
- Word/Excel 머리글/바닥글이 이미지나 필드 코드로만 들어간 경우 텍스트 추출이 되지 않아 실패할 수 있다. 운영 템플릿은 텍스트 머리글/바닥글을 유지하는 것이 좋다.
- Excel 숨김 시트도 현재 파서 기준으로 검사 대상이다.
- zip 내부 파일의 실제 생성일은 안정적으로 보존되지 않으므로 제품 스크린샷 날짜 검사는 zip entry 수정일자를 기준으로 한다.
- `test.zip`의 남은 11개 실패는 현재 기준으로 코드 문제가 아니라 테스트 문서/파일 수정 대상으로 본다.

## 바로 다음 작업

1. `test.zip`의 남은 11개 실패 항목은 실제 산출물 수정 후 `/download-review/` 또는 직접 검사 스크립트로 18개 전체 통과 여부를 확인한다.
2. 실제 PC 배포 절차를 정리한다. 현재 배포 대상은 `local_review_app/dist/GSCertLocalReview/` 폴더 전체다.
3. ECM 실제 다운로드 자동화는 이번에 수정하지 않았으므로, 별도 라이브 다운로드 테스트가 필요하면 worker 경로로 다시 확인한다.

## 결정 필요

1. 남은 11개 실패를 규칙 완화 없이 문서/파일 수정으로 처리할지 유지 결정한다.
   - 추천: 규칙은 유지한다. 현재 실패 항목은 앞서 확정한 규칙과 직접 연결되어 있어 완화하면 검증력이 떨어진다.
2. `test.zip` 수정 후 전체 통과 기준을 언제 운영 시간 복구 시점으로 볼지 정한다.
   - 추천: 샘플 zip 18개 전체 통과와 UI 결과 확인이 끝난 직후 `20:00-07:00`으로 복구한다.

## 2026-06-16 추가 반영

- 기대값 표시 매핑 문서는 `main/docs/22_expected_value_display_mapping.md`에 EV-001~EV-134 고정 번호로 정리했다.
- 합의서, 시험계획서, 시험성적서, 품질평가보고서, 적합평가보고서의 Word 파일 범위는 `.docx`에서 `.docx`, `.docm`으로 확대했다.
- 품질특성별 제품 정보 기재사항 제목 점검은 긴 고정 제목 대신 `{project_number}`와 `품질특성별` 문구가 함께 있는지 확인한다.
- 평가표 EV-100의 기능별 점검표 B~D와 기능적합성 A~C 비교 규칙은 제외했다.
- 결함리포트에서 산출하는 H값은 `시험분석자료` 시트에서 E열 값이 `H`이고 C열 값이 `-` 또는 공백이 아닌 행 개수로 산정한다.
