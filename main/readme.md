# main

## 역할

Django 프로젝트의 주요 웹 화면, URL, 정적 파일, 데이터 변환 유틸리티를 담는 앱 폴더다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `urls.py` | 사용자가 접근하는 HTTP URL과 view를 연결한다. |
| `views/init.py` | 주요 HTML 화면을 렌더링하는 기본 view 함수들을 모아 둔다. |
| `models.py` | main 앱의 Django 모델 정의 위치다. |
| `db_routers.py` | download-review 실행 이력 모델을 `workflow.db`로 라우팅한다. |
| `apps.py` | main 앱 설정과 시작 시 초기화 로직 위치다. |
| `consumers.py`, `routing.py` | Channels WebSocket 연결에 사용하는 파일이다. |

## 하위 폴더

| 폴더 | 설명 |
| --- | --- |
| `templates` | Django HTML 템플릿을 보관한다. |
| `static` | CSS, JavaScript, 이미지 파일을 보관한다. |
| `views` | 기능별 view와 파서 로직을 보관한다. |
| `services` | 화면/API에서 함께 쓰는 DB 조회와 비즈니스 로직을 보관한다. |
| `utils` | CSV, Excel, FAISS 등 데이터 변환 유틸리티를 보관한다. |
| `management` | Django management command를 보관한다. |
| `data` | `ecmlist.db`, `workflow.db` 등 로컬 DB 파일을 둘 위치다. Git 추적은 제외된다. |

## 주의사항

- 화면을 추가할 때는 `urls.py`, `views/init.py`, `templates`, `static` 파일의 역할을 함께 확인한다.
- 폴더나 주요 파일을 추가하면 관련 `readme.md`를 갱신한다.

## 관련 문서

- `08_ui_api_design.md`
- `11_readme_policy.md`
- `13_ui_mockup_design.md`
