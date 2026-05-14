# main/static/scripts

## 역할

화면별 JavaScript 파일과 기능 영역별 스크립트 폴더를 보관한다.

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `index.js` | 기존 메인 화면 동작을 담당한다. |
| `review/ecm_download_review.js` | ECM 제출물 자동 검사 mock UI의 mock 데이터, 탭 전환, 필터, 상태 표시를 담당한다. |

## 하위 폴더

| 폴더 | 설명 |
| --- | --- |
| `testing` | testing 영역 화면의 JavaScript를 보관한다. |
| `certy` | certy 영역 화면의 JavaScript를 보관한다. |
| `review` | review 영역 화면의 JavaScript를 보관한다. |

## 주의사항

- mock 데이터는 실제 API 연결 전까지 화면 검토 목적으로만 사용한다.
- 실제 API 연결 시 mock 데이터 구조와 API 응답 구조를 맞춰 불필요한 화면 수정이 생기지 않도록 한다.

## 관련 문서

- `main/docs/08_ui_api_design.md`
- `main/docs/13_ui_mockup_design.md`
