# main/docs

## 역할

이 폴더는 GSCert download-review 기능의 설계, 운영, 개발, 인수인계 문서를 보관한다.

처음 보는 사람은 개별 설계 문서를 바로 열기보다 `18_manual_index.md`부터 읽는 것이 좋다. 이 문서는 어떤 상황에서 어떤 문서를 봐야 하는지 안내하는 목차 역할을 한다.

## 문서 구분

| 구분 | 문서 | 용도 |
| --- | --- | --- |
| 빠른 인수인계 | `00_next_step.md` | 현재 브랜치, 최근 변경, 바로 다음 작업 |
| 사용자 친화 목차 | `18_manual_index.md` | 운영자/개발자/규칙 수정자가 어디부터 봐야 하는지 안내 |
| 점검규칙 매뉴얼 | `19_inspection_rule_manual.md` | `inspection_rule.config_json` 구조와 수정 방법 |
| 운영 매뉴얼 | `20_download_review_operations_manual.md` | 서버, worker, DB 동기화, rule seed, 검증 절차 |
| 개발 변경 매뉴얼 | `21_developer_change_manual.md` | 변경 유형별 수정 위치와 검증 체크리스트 |
| 설계 원문 | `01_*.md` ~ `17_*.md` | 세부 설계, 결정 기록, 과거 진행 내역 |
| 폴더 안내 | 각 폴더의 `readme.md` | 해당 폴더 안의 파일 역할 |
| Codex skill | `codex_skills/` | 다른 PC에서 이어받을 때 설치할 유지보수 skill 원본 |

## 주요 설계 문서

| 문서 | 역할 |
| --- | --- |
| `01_automation_flow.md` | 전체 자동화 흐름 |
| `02_database_design.md` | `ecmlist.db`, `ecmlist2.db`, `workflow.db` 구조 |
| `03_webpage1_automation.md` | ECM 웹 페이지 탐색 자동화 |
| `04_agent_download.md` | Windows agent 다운로드 팝업/폴더 선택 |
| `05_zip_inspection.md` | 다운로드 산출물 점검 규칙 설계 원문 |
| `06_recovery_and_lock.md` | lock, heartbeat, 실패 복구 |
| `07_skill_strategy.md` | Codex skill 운영 전략 |
| `08_ui_api_design.md` | `/download-review/` UI/API 계약 |
| `09_worker_process_design.md` | worker 처리 구조 |
| `10_operations_scripts.md` | 운영 PowerShell 스크립트 |
| `11_readme_policy.md` | readme 유지 정책 |
| `12_implementation_roadmap.md` | 단계별 구현 로드맵과 진행 상태 |
| `13_ui_mockup_design.md` | UI 목업 설계 |
| `14_dependency_management.md` | 의존성 관리 |
| `15_open_decisions.md` | 남은 결정 사항 |
| `16_backend_foundation_progress.md` | 백엔드 기반 작업 이력 |
| `16_download_review_backend_decisions.md` | 백엔드 결정 로그 |
| `17_llm_review_interface.md` | LLM 기반 점검 인터페이스 |

## 관리 기준

- `00_next_step.md`는 긴 설계 문서가 아니라, 바로 이어받기 위한 최신 상태만 남긴다.
- 새로 기능을 바꾸면 관련 설계 문서와 `18_manual_index.md`의 연결 정보가 맞는지 확인한다.
- 점검규칙 JSON을 바꾸거나 rule type을 추가하면 `19_inspection_rule_manual.md`를 먼저 갱신한다.
- 운영 절차, 명령어, DB 동기화 방식이 바뀌면 `20_download_review_operations_manual.md`를 갱신한다.
- 코드 위치나 검증 절차가 바뀌면 `21_developer_change_manual.md`를 갱신한다.
