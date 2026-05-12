# main/services

## 역할

view에서 직접 처리하기에는 커지는 DB 조회, 검증, 작업 생성 같은 서버 로직을 보관한다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `reference_db.py` | `main/data/ecmlist.db`의 `ecm_list` 테이블을 조회하고, allowlist 기반으로 점검 결과 컬럼만 갱신한다. |
| `download_review_jobs.py` | 작업 요청 JSON 검증, 완료/중복 프로젝트 차단, 예약/대기열 상태 결정, `workflow.db` 작업 생성과 polling API 응답 직렬화를 담당한다. |
| `download_review_worker.py` | worker가 시작 가능한 작업을 claim하고 프로젝트별 상태 전이를 수행한다. dry-run 모드와 실제 ECM 자동화 모드를 모두 지원한다. |
| `ecm_download.py` | ECM 웹페이지1에서 Playwright로 프로젝트 폴더 선택, 문서 전체 선택, 파일 다운로드 메뉴 클릭까지의 자동화를 수행한다. (5단계) |
| `ecm_selectors.py` | download-review 전용 CSS selector 상수를 관리한다. 기존 `playwright_job/selectors.py`와 분리된 별도 모듈이다. |
| `download_verify.py` | 다운로드된 폴더에서 파일 존재 여부, 개수, 0바이트 확인, 프로젝트번호 포함 여부를 검증한다. (9단계) |
| `agent_popup.py` | pywinauto를 사용하여 Windows '폴더 찾아보기' 팝업 처리, '전송현황' 창 대기, '시스템 알림'(중복 파일) 처리를 수행한다. (7~8단계) |

## 주의사항

- 외부 입력으로 SQL 식별자나 정렬식을 직접 만들지 말고 allowlist를 사용한다.
- `ecmlist.db`는 자동 생성하지 않는다. 파일이 없으면 오류로 처리한다.
- `번호`부터 `시험PL`까지의 기준정보 컬럼은 갱신하지 않는다.
- write-back은 `점검결과`와 산출물 점검 컬럼만 허용한다.
- `ecm_download.py`는 `playwright_job/`과 목적이 다르다. `playwright_job/`은 URL 복사용 자동화이고, `ecm_download.py`는 파일 다운로드용 자동화다.
- ECM 접속 URL과 timeout은 `myproject/settings.py`의 `ECM_BASE_URL`, `ECM_DOWNLOAD_TIMEOUTS`에서 관리한다.
