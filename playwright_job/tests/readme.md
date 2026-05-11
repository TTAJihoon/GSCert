# playwright_job/tests 폴더 가이드

이 폴더는 `playwright_job`의 단위 테스트를 둔다.

## 현재 테스트

- `test_reference_repository.py`: 임시 SQLite 파일을 만들어 `reference_repository.py`의 스키마 검증, 프로젝트번호 단건 조회, 목록 검색, 누락 DB 오류 처리를 확인한다.

## 작성 기준

- 외부 ECM 웹페이지나 브라우저 실행이 필요 없는 테스트를 우선 둔다.
- 실제 `main/data/reference.db`를 수정하지 않고 `tempfile`로 만든 임시 DB를 사용한다.
- Django 설정 import로 인해 무거운 초기화가 발생하지 않도록 순수 Python 테스트를 유지한다.
