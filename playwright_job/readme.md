# playwright_job 폴더 가이드

이 폴더는 외부 ECM 웹페이지 자동화와 작업 실행에 가까운 백엔드 코드를 모아둔다.

## 주요 파일

- `ecm.py`: Playwright로 ECM 페이지에 접속하고 폴더, 문서, 파일 목록을 단계별로 탐색하는 비동기 함수가 있다.
- `tasks.py`: ECM 자동화 단계를 작업 단위로 실행하고 실패 시 스크린샷과 단계 정보를 남기는 래퍼가 있다.
- `reference_repository.py`: `main/data/reference.db`의 `ecm` 테이블을 조회하는 저장소 계층이다. 프로젝트 목록 조회, 프로젝트번호 단건 조회, 스키마 검증을 담당한다.
- `selectors.py`: ECM 화면 자동화에 사용하는 CSS selector 상수를 둔다.
- `common.py`: URL, timeout, 날짜/프로젝트번호 처리 등 자동화 공통 유틸리티가 있다.
- `consumers.py`, `routing.py`: 기존 Django Channels 웹소켓 처리 코드다.
- `clipboard.py`, `parsers.py`, `url_cache.py`: 자동화 흐름에서 사용하는 보조 기능이다.
- `tests/`: Django 서버를 띄우지 않고 실행할 수 있는 순수 단위 테스트를 둔다.

## reference_repository.py 사용 기준

`reference.db`는 사용자가 별도로 준비하는 기준 데이터베이스이며 기본 위치는 `main/data/reference.db`다.

- 테이블 이름은 `ecm`이어야 한다.
- 컬럼명은 설계 문서의 공백 없는 한글 컬럼명을 그대로 사용한다.
- 모든 컬럼은 문자열로 다룬다.
- 조회 코드에서는 SQL 인젝션을 피하기 위해 지원하는 검색 조건만 허용한다.

현재 지원하는 검색 조건은 다음과 같다.

- `project_number`: `프로젝트번호`
- `company`: `회사명`
- `product`: `제품명`
- `test_pl`: `시험PL`
- `review_result`: `점검결과`

## 테스트

다음 명령으로 이 폴더의 순수 단위 테스트를 실행한다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover playwright_job/tests
```
