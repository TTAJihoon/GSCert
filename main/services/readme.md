# main/services

## 역할

view에서 직접 처리하기에는 커지는 DB 조회, 검증, 작업 생성 같은 서버 로직을 보관한다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `main/views/review/ecm_*.py` | ECM download-review 관련 Python 코드는 기존 review 영역 규칙에 맞춰 `main/views/review` 아래에 둔다. |

## 주의사항

- 외부 입력으로 SQL 식별자나 정렬식을 직접 만들지 말고 allowlist를 사용한다.
- `ecmlist.db`는 자동 생성하지 않는다. 파일이 없으면 오류로 처리한다.
- `번호`부터 `시험PL`까지의 기준정보 컬럼은 갱신하지 않는다.
- write-back은 `점검결과`와 산출물 점검 컬럼만 허용한다.
- `main/views/review/ecm_download.py`는 `playwright_job/`과 목적이 다르다. `playwright_job/`은 URL 복사용 자동화이고, `ecm_download.py`는 파일 다운로드용 자동화다.
- ECM 접속 URL과 timeout은 `myproject/settings.py`의 `ECM_BASE_URL`, `ECM_DOWNLOAD_TIMEOUTS`에서 관리한다.
