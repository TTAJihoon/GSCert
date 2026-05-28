# GSCert 문서 목차와 사용 가이드

## 이 문서의 목적

이 문서는 흩어진 Markdown 문서를 사용자 친화적으로 찾아가기 위한 입구다.

기존 `01_*.md` ~ `17_*.md` 문서는 설계 원문과 결정 기록에 가깝다. 실제로 운영하거나 수정할 때는 아래 매뉴얼 문서부터 보고, 필요한 경우 설계 원문으로 내려가면 된다.

## 먼저 어디를 볼까

| 상황 | 먼저 볼 문서 | 이어서 볼 문서 |
| --- | --- | --- |
| 다른 PC에서 바로 이어받기 | `00_next_step.md` | `20_download_review_operations_manual.md` |
| 점검규칙 JSON을 수정하기 | `19_inspection_rule_manual.md` | `05_zip_inspection.md`, `02_database_design.md` |
| 서버/worker를 실행하거나 상태 확인하기 | `20_download_review_operations_manual.md` | `10_operations_scripts.md`, `09_worker_process_design.md` |
| Google Sheet 동기화와 WD 컬럼 확인하기 | `20_download_review_operations_manual.md` | `main/utils/ecmList/readme.md`, `02_database_design.md` |
| API나 화면을 수정하기 | `21_developer_change_manual.md` | `08_ui_api_design.md`, `13_ui_mockup_design.md` |
| ECM 다운로드 자동화를 수정하기 | `21_developer_change_manual.md` | `03_webpage1_automation.md`, `04_agent_download.md` |
| lock, 재시도, 실패 복구를 확인하기 | `06_recovery_and_lock.md` | `09_worker_process_design.md` |
| LLM 점검을 검토하기 | `17_llm_review_interface.md` | `05_zip_inspection.md` |
| 남은 결정 사항을 확인하기 | `15_open_decisions.md` | `12_implementation_roadmap.md` |

## 문서 지도

### 1. 인수인계와 현재 상태

- `00_next_step.md`: 현재 브랜치, 최신 변경, 검증 결과, 바로 다음 작업.
- `18_manual_index.md`: 지금 보고 있는 문서. 전체 문서의 목차.

### 2. 점검규칙

- `19_inspection_rule_manual.md`: 점검규칙 JSON 구조, 수정 방법, 테스트 방법.
- `05_zip_inspection.md`: 산출물 점검 설계 원문과 구현 상태.
- `02_database_design.md`: `inspection_rule`, `inspection_result`, `ecm_list` 관계.
- `main/docs/codex_skills/gscert-download-review-maintainer/references/rules.md`: Codex skill에 포함되는 규칙 요약본.

현재 실제 구현된 산출물 규칙은 1~5번이다.

| 번호 | 산출물 컬럼 | 현재 구현 |
| --- | --- | --- |
| 1 | 계약서 | 파일명/폴더/확장자/개수 검사 |
| 2 | 합의서(PDF) | docx/pdf 존재 및 시험신청번호 검사 |
| 3 | 수수료산정표 | 파일명/폴더/확장자/개수 검사 |
| 4 | 시험환경구성도 | 파일명/폴더/개수 검사 |
| 5 | 품질특성별제품정보기재사항 | docx 제목/날짜 검사 |

6번 기능리스트와 7번 시험계획서(PDF)는 다음 구현 우선순위다.

### 3. 운영

- `20_download_review_operations_manual.md`: 서버 실행, worker 실행, Google Sheet 동기화, rule seed, 검증 명령.
- `10_operations_scripts.md`: 운영 PowerShell 스크립트 설계.
- `main/data/README.md`: DB 파일 보관 정책.
- `main/utils/ecmList/readme.md`: Google Sheet -> `ecmlist.db` 동기화 도구.

운영에서 특히 구분해야 할 DB는 다음과 같다.

| DB | Git 관리 | 용도 |
| --- | --- | --- |
| `main/data/ecmlist.db` | 관리 대상 | 상암 기준 프로젝트 목록과 점검 결과 컬럼 |
| `main/data/ecmlist2.db` | 관리 대상 | 영남 기준 프로젝트 목록과 점검 결과 컬럼 |
| `main/data/workflow.db` | 로컬 실행 DB | 작업, worker, 점검규칙, 점검결과 |
| `main/data/reference.db` | 관리 대상 | 기존 이력/제품정보 조회용 DB |

### 4. 개발

- `21_developer_change_manual.md`: 변경 유형별 수정 위치와 검증 체크리스트.
- `08_ui_api_design.md`: `/download-review/` UI/API 계약.
- `09_worker_process_design.md`: worker 처리 흐름.
- `12_implementation_roadmap.md`: 단계별 구현 로드맵.
- `15_open_decisions.md`: 아직 결정이 필요한 항목.

### 5. ECM 자동화

- `03_webpage1_automation.md`: ECM 웹 페이지 선택자와 탐색 방식.
- `04_agent_download.md`: Windows agent 다운로드 팝업, 폴더 선택, 중복 파일 알림 처리.
- `06_recovery_and_lock.md`: ECM/Playwright/clipboard 공통 lock과 실패 복구.

### 6. 폴더별 readme

| 문서 | 역할 |
| --- | --- |
| `main/readme.md` | Django app 전체 폴더 지도 |
| `main/views/readme.md` | view 계층 지도 |
| `main/views/review/ecm_download_review_readme.md` | download-review 관련 view 파일 지도 |
| `main/templates/readme.md` | 템플릿 폴더 지도 |
| `main/static/readme.md` | 정적 파일 폴더 지도 |
| `main/static/scripts/readme.md` | JavaScript 파일 지도 |
| `main/static/css/readme.md` | CSS 파일 지도 |
| `main/data/README.md` | DB/엑셀 데이터 파일 정책 |
| `main/utils/ecmList/readme.md` | Google Sheet 동기화 도구 |
| `playwright_job/readme.md` | 기존 Playwright job 영역 |
| `playwright_job/tests/readme.md` | 기존 Playwright 테스트 영역 |

## 문서 유지 원칙

- 새 기능을 만들면 “실제 사용자가 어디서 알 수 있는지”를 먼저 생각한다.
- 변경 설명은 설계 원문에만 묻어두지 말고, 관련 매뉴얼에도 반영한다.
- 점검규칙은 `19_inspection_rule_manual.md`가 최신이어야 한다.
- 운영 명령어는 `20_download_review_operations_manual.md`가 최신이어야 한다.
- 코드 위치와 검증 절차는 `21_developer_change_manual.md`가 최신이어야 한다.
- 오래된 설계 문서는 삭제하지 않고, 새 목차에서 “설계 원문” 또는 “이력 문서”로 분리한다.
