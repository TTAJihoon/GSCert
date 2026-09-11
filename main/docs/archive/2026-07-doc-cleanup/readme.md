# 2026-07 문서 정리 archive

## 목적

이 폴더는 `main/docs` 루트에서 제외한 과거 설계 원문, 진행 로그, 중복 문서를 보관한다.

문서를 삭제하지 않고 보관한 이유는 과거 Playwright/agent 구현 배경이나 결정 근거가 문제 분석에 필요할 수 있기 때문이다. 최신 절차는 루트 문서를 우선한다.

## 보관 문서와 현재 기준 문서

| 보관 문서 | 현재 먼저 볼 문서 |
| --- | --- |
| `01_automation_flow.md` | `../../00_README.md`, `../../01_operations.md` |
| `02_database_design.md` | `../../04_data_and_api.md` |
| `03_webpage1_automation.md` | `../../06_artifact_source_ecm.md`, `../ADR/2026-07-http-ecm-source.md` |
| `04_agent_download.md` | `../../06_artifact_source_ecm.md`, `../ADR/2026-07-http-ecm-source.md` |
| `05_zip_inspection.md` | `../../02_inspection_rules.md` |
| `06_recovery_and_lock.md` | `../../01_operations.md` |
| `07_skill_strategy.md` | `../../codex_skills/README.md` |
| `08_ui_api_design.md` | `../../03_developer_guide.md` |
| `09_worker_process_design.md` | `../../01_operations.md` |
| `10_operations_scripts.md` | `../../01_operations.md` |
| `11_readme_policy.md` | `../../00_README.md` |
| `12_implementation_roadmap.md` | `../../00_README.md`, `../../00_README.md` |
| `13_ui_mockup_design.md` | `../../03_developer_guide.md` |
| `14_dependency_management.md` | `../../01_operations.md` |
| `16_backend_foundation_progress.md` | `../../00_README.md` |
| `16_download_review_backend_decisions.md` | `../../00_README.md`, `../../04_data_and_api.md` |
| `17_llm_review_interface.md` | `../../00_README.md` |
| `22_expected_value_display_mapping.md` | `../../02_inspection_rules.md`, `../../../../gscert_review_core/result_display.py` |
| `23_local_desktop_postgresql_design.md` | `../../04_data_and_api.md`, `../../04_data_and_api.md` |
| `29_download_review_split_server_deployment.md` | `../ADR/2026-07-http-ecm-source.md` |
| `30_ecm_center_navigation_plan.md` | `../../06_artifact_source_ecm.md`, `../ADR/2026-07-http-ecm-source.md` |
| `31_test_zip_ecm_flow_simulation.md` | `../../01_operations.md`, `../../02_inspection_rules.md` |
| `32_ecm_integration_reference.md` | `../ADR/2026-07-http-ecm-source.md` |
| `32_google_sheet_reference_project_postgres_sync.md` | `../../04_data_and_api.md`, `../../04_data_and_api.md` |

## 사용 기준

- 최신 운영/개발 절차는 루트 문서를 따른다.
- archive 문서는 과거 구현 의도, 실패 원인, 레거시 Playwright/agent 동작을 확인할 때만 참고한다.
- archive 문서를 다시 루트로 이동하기 전에는 중복되는 최신 문서가 없는지 확인한다.
