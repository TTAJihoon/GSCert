# GSCert Next Step

## 현재 기준

- 작업 브랜치: `codex-job-runner-persistence`
- 다운로드 점검 화면: `http://127.0.0.1:8000/download-review/`
- 개발 서버 예시:
  ```powershell
  .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings --noreload
  ```
- 점검 규칙 1~18번은 실제 규칙으로 구현되어 있으며, `seed_download_review_rules --only-real --enable --update-existing` 기준으로 운영 DB에 반영한다.
- Windows 로컬 앱 배포 ZIP은 `GET /api/local-review/app/download/`에서 `C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard` 폴더를 스트리밍한다.

## 최신 변경 요약

- `{버전}` 파싱 기준을 완화했다.
  - `v1`, `v1.0`, `ver 3.0`, 숫자 버전 `1`, `3.0`, 문자 버전 `Enterprise`를 버전으로 본다.
  - `EBS ISM3.0`처럼 마지막 단어에 문자와 숫자가 붙으면 제품명은 `EBS ISM`, 버전은 `3.0`으로 분리한다.
  - 시험계획서 버전 비교는 숫자 버전의 `v`/`ver` 접두사를 무시하고, 문자 버전은 공백과 대소문자를 무시한다.
- 결함리포트 시트 구성 비교는 시트명의 공백을 제거한 뒤 비교한다. 예: `1차 결함리포트`와 `1차결함리포트`는 같은 시트명이다.
- download-review 규칙 결과 모달에서 `산출물` 열을 제거했다.
- 규칙 결과 모달의 `HTML 다운로드` 버튼 왼쪽에 `전체 폴더 다운로드` 버튼을 추가했다.
  - 버튼은 `POST /api/projects/<프로젝트번호>/full-documents-download/`를 호출한다.
  - 서버는 기존 시험 이력 조회의 `download_full_project_documents()` 흐름으로 ECM 전체 폴더 ZIP을 준비하고 `/history/report/<프로젝트번호>/download/` 링크를 반환한다.

## 바로 다음 작업

1. 실제 샘플 ZIP 또는 운영 ECM 프로젝트로 9-6 버전 추출, 10번 결함리포트 시트명 공백 무시, 모달 전체 폴더 다운로드를 브라우저에서 확인한다.
2. UI 변경 후 서버를 재시작하고 `/download-review/`에서 정적 파일 `?v=23`이 로드되는지 확인한다.
3. live 테스트가 끝나면 download-review 작업 시작 시간 제한을 운영 기준 `20:00-07:00`으로 되돌린다.

## 기본 검증 명령

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```
