# GSCert Download Review

`main/docs`의 진입 문서다. 현재 시스템 상태, 문서 지도, 남은 작업, 미결사항만 여기에 둔다. 세부 절차는 각 기준 문서에 있고 이 문서는 내용을 복사하지 않는다.

## 현재 운영 구조

| 항목 | 현재 기준 |
| --- | --- |
| 운영 진입점 | 194 서버(`210.96.71.194`)의 `/download-review/`. 241 서버는 요청을 194로 넘기는 보조 경로 |
| 산출물 source | `ecm-http`(서버측 `requests` HTTP 직접연동)가 기본값. `local`은 ECM 없이 전체 흐름을 돌리는 fake-live용. 레거시 Playwright source는 코드에서 제거됐고 `ecm` 값은 `ecm-http` 별칭 |
| 워커 | 194 워커 1개가 분당·상암·영남 세 센터를 모두 처리 |
| DB | `reference`(PostgreSQL, 공유 기준정보·규칙·수동 적합 메모) / `workflow`(SQLite, 서버 로컬 실행 상태) / `default`(SQLite, Django 기본) |
| 점검규칙 | 1~18번(`artifact_01`~`artifact_18`) 구현. 반영은 `seed_download_review_rules --only-real --enable --update-existing` |
| 점검 엔진 | 웹과 Windows 앱이 `gscert_review_core.engine`을 공유(현재 엔진 버전 `0.2.0`) |
| Windows 앱 | `local_review_app`의 `GSCertLocalReviewDashboard`. 서버에서 규칙 bundle을 받아 로컬 폴더를 점검 |
| 작업 시작 제한 | 없음. 새 작업은 즉시 `queued`. 단 서버 시간이 임시 변경 중이면 정상 복구까지 워커가 claim하지 않는다 |
| 서버 시간 제어 | 194가 WinRM으로 85(`210.96.71.85`)의 OS 시각만 변경한다. 194 자신의 시각은 바뀌지 않는다 |
| 센터 기본 선택 | 접속 IP가 `210.96.0.0/16`이면 상암, `210.104.0.0/16`이면 분당. URL `?center=`가 우선 |

## 문서 안내

| 상황 | 볼 문서 |
| --- | --- |
| 서버·워커를 실행하거나 운영 장애를 확인 | `01_operations.md` |
| 점검규칙의 판정 기준을 확인하거나 규칙을 수정 | `02_inspection_rules.md` |
| 코드를 변경할 위치와 검증 절차를 찾기 | `03_developer_guide.md` |
| DB 컬럼·API 계약·기준정보 동기화를 확인 | `04_data_and_api.md` |
| Windows 로컬 앱을 실행·테스트·배포 | `05_windows_local_app.md` |
| 산출물 source(ECM/로컬) 구조를 확인하거나 새 저장소를 붙이기 | `06_artifact_source_ecm.md` |
| ECM 서버 시간 임시 변경을 점검 | `07_server_time_control.md` |
| 산출물 자동 입력 기능을 설계·진행 | `08_artifact_autofill.md` |
| 과거에 왜 그렇게 결정했는지 찾기 | `archive/ADR/` |
| 과거 완료 내역을 찾기 | `archive/changelog/`, `git log` |

각 정보의 기록 위치는 한 곳으로 고정한다.

| 정보 | 기록 위치 |
| --- | --- |
| 현재 전체 상태, 남은 작업, 미결사항 | 이 문서 |
| 운영 명령과 장애 대응 | `01_operations.md` |
| 규칙의 실제 판정 동작 | `02_inspection_rules.md` |
| DB 컬럼 정의와 API 계약 | `04_data_and_api.md` |
| ECM source 현재 구조 | `06_artifact_source_ecm.md` |
| 과거 의사결정 배경 | `archive/ADR/` |
| 과거 완료 내역 | `archive/changelog/` 또는 git 이력 |

## 현재 다음 작업

1. 194 서버에서 로컬 앱 배포 폴더(`local_review_app/dist/GSCertLocalReviewDashboard`)를 재빌드하고 HTTPS 연결을 확인한다.
2. 운영 ECM 프로젝트 1건으로 세부항목 단위 수동 적합 저장, 보라색 테두리 정상 배지, 재점검 재적용을 브라우저에서 확인한다.
3. 같은 프로젝트에서 전체 산출물 다운로드 스트리밍, `수정 내용` 팝업, 파일명 개정 버전 dedup을 확인한다.
4. 85 서버에서 실제 OS 시간 변경·자동 복구·재부팅 복구를 live 검증한다. WinRM 연결과 dry-run은 확인됐지만 실제 시각 변경은 아직 실행하지 않았다(85는 실사용 ECM 시스템).
5. 산출물 자동 입력 기능의 공통 변수 조회 경로를 정리한다(`08_artifact_autofill.md`).

## 미결사항

| 항목 | 내용 |
| --- | --- |
| `{인증위}` 기대값 출처 | `reference_project`에 `cert_committee_date` 컬럼이 있지만 레거시 `sync_reference_projects_from_sheet`만 채우고, 점검 엔진은 이 컬럼을 읽지 않는다(프로젝트 목록 정렬에만 사용). 엔진이 쓰는 `cert_date`에는 동기화 경로에 따라 인증서 발급일 또는 인증위 개최일이 섞여 들어간다. 어느 값을 기준으로 삼을지 결정이 필요하다. 상세: `08_artifact_autofill.md` |
| 분당/영남 "GS 정보 확인용" 시트 | `main/utils/google_sheet_reference.py`의 `SOURCES`에 상암 시트만 등록돼 있다. 두 센터 시트가 등록되어야 자동 입력 공통 변수를 채울 수 있다 |
| 자동 입력용 공통 변수 조회 경로 | 점검 엔진은 현재 `ecm_row_json`/`SwData`(인증획득목록 엑셀)를 본다. 신규 시트로 교체할지, 자동 입력 전용 경로를 새로 만들지 결정이 필요하다 |
| 상암/영남 ECM root OID 실측 기록 | 현재 194가 세 센터를 `ecm-http`로 처리하고 있어 실질 문제는 확인되지 않았지만, 센터별 `verify_ecm_http --download` 실측 결과가 문서에 남아 있지 않다 |
| 샘플 zip 잔여 실패 처리 | 규칙을 완화하지 않고 산출물을 수정해 통과시키는 방향을 기준으로 한다. 실제 운영 양식 차이가 확인된 항목만 규칙을 조정한다 |
| archive 보관 기간 | `archive/`의 과거 설계·결정·변경 이력 문서를 언제까지 보관할지 정하지 않았다. 현재는 삭제하지 않는다 |

## 최근 주요 변경

오래된 항목은 `archive/changelog/`와 git 이력에서 본다.

- 산출물 다운로드를 `ecm-http` HTTP 직접연동 단일 경로로 전환하고 레거시 Playwright source를 제거했다.
- 수동 적합 처리를 세부항목 단위로 `inspection_manual_override`(reference DB)에 저장하고 재점검에서 다시 적용한다.
- 서버 시간 임시 변경 기능(194→85 WinRM, `GSCertTimeControl` 서비스, 3분 lease, 4자리 PIN)을 구현했다.
- 기존 `20:00~07:00` 작업 시작 제한을 폐기했다. 새 작업은 즉시 `queued`가 된다.
- 전체 산출물 다운로드를 GET attachment ZIP 스트리밍으로 바꿔 압축 완료를 기다리지 않게 했다.
- 산출물 파일명 개정 버전(`v1.0`/`v1.1` 등)을 파싱해 같은 산출물은 major별 최신 minor만 점검한다.
- 규칙 결과 모달에서 `기대값`/`실제값`을 별도 컬럼으로 분리했다.
- Windows 로컬 앱 배포본을 `GSCertLocalReviewDashboard`로 통일하고 HTTPS 번들 인증서를 `gsai.tta.or.kr` 인증서로 교체했다.
- 산출물 자동 입력 기능 설계를 시작했다(`08_artifact_autofill.md`).

## 문서 관리 기준

- 완료된 작업을 이 문서에 계속 누적하지 않는다. "최근 주요 변경"은 10개 이내로 유지하고 넘치면 `archive/changelog/`로 옮긴다.
- 같은 정보를 두 문서에 쓰지 않는다. 다른 문서에서는 `DB 구조는 04_data_and_api.md 참고`처럼 링크만 남긴다.
- 각 문서에 `현재 상태`, `구현 완료`, `다음 작업`을 따로 적지 않는다. 그 정보는 이 문서에만 둔다.
- ADR(결정 기록)은 당시 판단을 그대로 보존한다. 최신 상태와 어긋나도 수정하지 않고, 현재 기준은 해당 기준 문서에서 갱신한다.
- 규칙을 바꾸면 `02_inspection_rules.md`, DB 구조를 바꾸면 `04_data_and_api.md`, 운영 절차를 바꾸면 `01_operations.md`를 갱신한다.
- 문서만 수정해도 `git diff --check`로 공백 오류를 확인한다.
