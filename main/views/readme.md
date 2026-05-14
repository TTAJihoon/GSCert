# main/views

## 역할

HTTP 요청을 처리하는 Django view 함수와 문서 파싱, GPT 연동 등 기능별 서버 로직을 보관한다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `init.py` | 주요 HTML 템플릿을 렌더링하는 기본 view 함수들을 모아 둔다. `/download-review/` 목업 화면도 이 파일에서 렌더링한다. |
| `review/ecm_download_review_api.py` | download-review 화면에서 사용할 프로젝트 목록 API와 이후 작업/결과 API를 보관한다. |
| `review/ecm_*.py` | ECM 제출물 자동 다운로드, worker, 기준 DB 조회, 파일 검증 등 download-review Python 코드를 보관한다. |

## 하위 폴더

| 폴더 | 설명 |
| --- | --- |
| `testing` | Testing 영역의 이력 조회, 유사 제품 조회, 보안 리포트 관련 view와 보조 로직을 보관한다. |
| `certy` | Certy 영역의 제품정보 생성, 파일 파싱, 다운로드 관련 view와 보조 로직을 보관한다. |
| `review` | Review 영역의 시험결과서 파싱, PDF/DOCX 처리, GPT 점검 관련 로직을 보관한다. |

## 주의사항

- 화면 렌더링만 담당하는 view와 실제 처리 로직은 가능하면 분리한다.
- URL을 추가하면 `main/urls.py`와 연결되는 view 함수 위치를 함께 확인한다.
- 외부 API 키가 필요한 모듈은 import 시점에 즉시 클라이언트를 만들지 않도록 주의한다.

## 관련 문서

- `main/docs/08_ui_api_design.md`
- `main/docs/13_ui_mockup_design.md`
