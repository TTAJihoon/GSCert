# 남은 고민과 확정 필요 항목

## 목적

다른 대화창이나 이후 작업자가 현재 남은 판단 지점을 빠르게 확인하도록 정리한다.

과거의 긴 결정 로그는 `archive/2026-07-doc-cleanup/`에 보관했다. 이미 완료된 기능 변경은 `14_completed_download_review_changes.md`로 분리하고, 이 문서에는 지금 기준으로 실제로 확인하거나 결정해야 할 항목만 남긴다.

## 현재 진행 상태

- 브랜치: `codex-job-runner-persistence`
- download-review는 194 서버 단일 처리와 `ecm-http` source를 기준으로 운영한다.
- 점검규칙 1~18번은 구현되어 있고, 웹과 Windows 앱은 공용 규칙 DB/API/엔진을 사용한다.
- 기준 프로젝트, PL 매핑, 점검규칙, 수동 적합 메모는 공유 PostgreSQL `reference` DB를 기준으로 본다.
- 작업 상태, 점검 결과 원본, 유사 분석 작업은 서버 로컬 `workflow.db`에 저장한다.

## 결정/확인 필요

### 1. `ecm-http` 실서버 검증 완료 기준

확인할 것:

- 분당, 상암, 영남 각각에서 프로젝트 폴더 탐색이 안정적으로 되는지.
- `verify_ecm_http --download` 결과가 파일 수와 byte 검증까지 통과하는지.
- 194 워커가 `source=ecm-http`로 떠 있을 때 세 센터 작업을 모두 처리하는지.

권장:

- 센터별 대표 프로젝트 1건 이상으로 실측한 뒤 `DOWNLOAD_REVIEW_SOURCE=ecm-http`를 기본 운영값으로 확정한다.

관련 문서:

- `12_http_ecm_source_decisions.md`
- `11_artifact_source_boundary.md`
- `04_download_review_operations_manual.md`

### 2. download-review 시간 제한 복구 시점

현재 테스트 편의를 위해 작업 가능 시간이 `00:00-24:00`으로 열려 있다.

결정할 것:

- 실서버 ECM HTTP 검증과 샘플 zip 확인이 끝난 직후 `20:00-07:00`으로 되돌릴지.

권장:

- 라이브 검증이 끝나면 즉시 운영 시간으로 복구한다.

관련 마커:

- `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`

### 3. 샘플 zip의 남은 실패 처리 방식

현재 기준:

- 규칙 1~18번은 코드 기준으로 동작한다.
- 남은 실패는 대부분 문서/파일 내용 불일치나 누락으로 본다.

결정할 것:

- 규칙 완화 없이 산출물을 수정해 통과시킬지.
- 실제 운영 양식이 다르다면 어느 항목만 규칙을 조정할지.

권장:

- 먼저 산출물 수정으로 처리한다. 규칙 완화는 실제 운영 양식 차이가 확인될 때만 한다.

관련 문서:

- `03_inspection_rule_manual.md`
- `09_rule_db_edit_quick_guide.md`

### 4. 문서 archive 유지 방식

과거 설계 문서는 삭제하지 않고 archive로 이동했다.

결정할 것:

- archive 문서를 일정 기간 보관 후 삭제할지.
- 계속 보관하되 검색 대상에서만 제외할지.

권장:

- 당장은 삭제하지 않는다. 과거 Playwright/agent 설계가 문제 분석에 필요할 수 있으므로 `archive/2026-07-doc-cleanup/`에 보관한다.

## 다음 작업 후보

1. 센터별 `verify_ecm_http --download` 실측.
2. 샘플 zip 1~18번 전체 통과 재확인.
3. 운영 시간 제한 `20:00-07:00` 복구.
4. 문서 archive 구조가 충분한지 한 번 더 확인.
