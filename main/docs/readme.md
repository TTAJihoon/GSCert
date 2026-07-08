# main/docs

## 역할

이 폴더는 GSCert download-review 기능의 최신 인수인계, 운영, 개발, 점검규칙 문서를 보관한다.

처음 보는 사람은 개별 설계 문서를 바로 열지 말고 `01_manual_index.md`를 먼저 본다. `00_next_step.md`는 현재 상태와 바로 다음 작업만 담는 짧은 인수인계 문서로 유지한다.

## 현재 사용하는 문서

| 구분 | 문서 | 용도 |
| --- | --- | --- |
| 빠른 인수인계 | `00_next_step.md` | 현재 브랜치, 최신 상태, 바로 다음 작업 |
| 전체 목차 | `01_manual_index.md` | 상황별로 어느 문서를 볼지 안내 |
| 남은 결정 | `02_open_decisions.md` | 아직 확정/검증이 필요한 항목 |
| 점검규칙 | `03_inspection_rule_manual.md` | 1~18번 점검규칙의 단일 기준 문서 |
| 운영 | `04_download_review_operations_manual.md` | 서버, worker, ECM HTTP, 검증 명령 |
| 개발 | `05_developer_change_manual.md` | 변경 유형별 수정 위치와 검증 체크리스트 |
| PostgreSQL/API | `06_postgresql_api_access_manual.md` | 기준정보/프로젝트 조회 API 사용법 |
| Windows 앱 | `07_local_windows_app_test_manual.md` | 로컬 점검 앱 실행, 테스트, 패키징 |
| 규칙 공유 구조 | `08_rulebase_shared_architecture.md` | 웹/Windows 앱의 공용 규칙 엔진 구조 |
| 규칙 DB 수정 | `09_rule_db_edit_quick_guide.md` | `inspection_rule` 수정 절차 |
| 기준 프로젝트 동기화 | `10_reference_project_sheet_sync.md` | Google Sheet -> `reference_project` 적재 |
| 산출물 source 경계 | `11_artifact_source_boundary.md` | ECM/로컬/다른 저장소 source 추가 기준 |
| ECM HTTP 결정 | `12_http_ecm_source_decisions.md` | Playwright -> HTTP 직접연동 ADR |
| DB 스키마 | `13_db_schema.md` | `default`/`workflow`/`reference` DB와 테이블 구조 |
| Codex skill | `codex_skills/` | 다른 PC에서 이어받을 때 설치할 유지보수 skill 원본 |

## 보관 문서

과거 설계 원문, 진행 로그, 중복된 설계 초안은 삭제하지 않고 아래로 이동했다.

```text
main/docs/archive/2026-07-doc-cleanup/
```

보관 문서의 전체 목록과 대체해서 볼 최신 문서는 `archive/2026-07-doc-cleanup/readme.md`에 정리한다.

## 관리 기준

- `00_next_step.md`는 누적 이력이 아니라 최신 인수인계만 남긴다.
- 점검규칙을 바꾸면 `03_inspection_rule_manual.md`와 `09_rule_db_edit_quick_guide.md`를 확인한다.
- 운영 절차, 환경변수, worker 실행 방식이 바뀌면 `04_download_review_operations_manual.md`를 갱신한다.
- 코드 위치나 검증 절차가 바뀌면 `05_developer_change_manual.md`를 갱신한다.
- DB 구조가 바뀌면 `13_db_schema.md`를 갱신한다.
- 오래된 설계 문서는 루트로 되돌리기보다 archive 문서에서 최신 문서로 연결한다.
