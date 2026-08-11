# main/templates

## 역할

Django가 렌더링하는 HTML 템플릿을 보관한다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `header.html` | 여러 화면에서 사용할 수 있는 헤더 템플릿이다. |
| `testing/history.html` | 사이트 루트(`/`)가 연결되는 메인 화면이다. |
| `review/ecm_download_review.html` | ECM 제출물 자동 검사 mock UI 화면이다. 직접 URL `/download-review/`로 검토한다. |
| `welcome.html` | 로그인 후 환영 화면이다. |

## 하위 폴더

| 폴더 | 설명 |
| --- | --- |
| `testing` | testing 영역 화면 템플릿을 보관한다. |
| `certy` | certy 영역 화면 템플릿을 보관한다. |
| `review` | review 영역 화면 템플릿을 보관한다. |
| `registration` | Django 로그인 화면 템플릿을 보관한다. |

## 주의사항

- 새 화면을 추가할 때는 연결되는 CSS와 JavaScript 위치를 함께 문서화한다.
- mock UI는 실제 API 연결 전 사용성 검토를 위한 화면이므로, API 연결 시 문구와 데이터 흐름을 다시 확인한다.

## 관련 문서

- `main/docs/13_ui_mockup_design.md`
