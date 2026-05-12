# main/services

## 역할

view에서 직접 처리하기에는 커지는 DB 조회, 검증, 작업 생성 같은 서버 로직을 보관한다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `reference_db.py` | `main/data/ecmlist.db`의 `ecm_list` 테이블을 read-only로 조회하고 `/api/projects/` 응답 형태로 정규화한다. |
| `download_review_jobs.py` | 작업 요청 JSON 검증, 완료/중복 프로젝트 차단, 예약/대기열 상태 결정, `workflow.db` 작업 생성과 polling API 응답 직렬화를 담당한다. |
| `download_review_worker.py` | worker가 시작 가능한 작업을 claim하고 dry-run 상태 전이와 샘플 점검결과 저장을 수행한다. |

## 주의사항

- 외부 입력으로 SQL 식별자나 정렬식을 직접 만들지 말고 allowlist를 사용한다.
- `ecmlist.db`는 자동 생성하지 않는다. 파일이 없으면 오류로 처리한다.
