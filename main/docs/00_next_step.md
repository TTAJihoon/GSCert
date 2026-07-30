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
- 규칙 결과 모달의 `HTML 다운로드` 버튼 왼쪽에 `전체 산출물 다운로드` 버튼을 추가했다.
  - 버튼은 `GET /api/projects/<프로젝트번호>/full-documents-download/?cert_date=...`를 직접 열어 브라우저 다운로드를 즉시 시작한다.
  - 서버는 ECM 전체 폴더 파일을 ZIP 엔트리 단위로 스트리밍한다. 첫 파일의 ZIP 헤더를 먼저 보내므로 전체 압축 완료를 기다리지 않고 다운로드 요청이 시작된다.
  - 앞으로 같은 기능을 재사용할 때는 JS의 `startFullProjectFolderDownload(project)` 헬퍼 또는 같은 GET attachment 엔드포인트를 사용한다. `fetch/POST -> JSON download_url` 방식은 브라우저 다운로드 시작을 늦추므로 UI에서는 쓰지 않는다.
- ECM 산출물 파일명 끝의 개정 버전(`v1`, `v1.0`, `v1.1`, `1.1` 등)을 파싱해 중복 후보를 정리한다.
  - 같은 산출물은 major별 최신 minor만 남긴다. 예: `기능리스트 v1.0`과 `기능리스트 v1.1`이 있으면 `v1.1`만 검사한다.
  - 결함리포트는 major 차수별로 최신 minor를 유지한다. 예: `v1.0`, `v1.1`, `v2.0`이면 `v1.1`, `v2.0`을 검사한다.
  - 새 버전 파일이 기존 산출물 폴더 밖에 추가되어도, 기존 폴더의 같은 산출물 후보와 같은 이름 그룹이면 최신 파일을 검사 대상으로 끌어온다.
- 규칙 결과 모달의 `전체 산출물 다운로드` 왼쪽에 `수정 내용` 버튼을 추가했다.
  - 기본 비활성화 상태이며, ECM 다운로드 파일 또는 보관/로그에서 `수정 내용.txt`가 발견되면 활성화된다.
  - 버튼은 `GET /api/job-projects/<job_project_id>/change-note/`로 txt 본문을 조회해 팝업에 표시한다.
- 규칙 결과 모달에서 `정상`이 아닌 결과 배지를 클릭하면 수동 적합 처리할 수 있다.
  - `POST /api/rule-results/<result_id>/manual-pass/`는 빈 메모를 거부하고, 사유 메모를 `inspection_manual_override`에 센터/프로젝트번호/규칙코드 기준으로 저장한다.
  - 수동 적합 결과는 상태값은 `pass`로 집계하되 `manual_override` 메타데이터를 함께 내려, UI에서 보라색 정상 배지로 표시한다. 정상 항목 필터에는 포함된다.
  - 다음 점검에서도 같은 센터/프로젝트번호/규칙코드 override가 있으면 자동 점검 결과와 관계없이 동일 메모로 수동 적합을 다시 적용한다.
- `프로젝트 선택`, `현재 작업 진행 상황`, `작업 조회` 탭은 클릭해 이동할 때마다 해당 탭 데이터를 다시 조회한다.

## 바로 다음 작업

1. 실제 샘플 ZIP 또는 운영 ECM 프로젝트로 파일명 개정 버전 dedup, 9-6 버전 추출, 10번 결함리포트 시트명 공백 무시, `수정 내용` 팝업, 모달 전체 산출물 다운로드 스트리밍, 수동 적합 처리/재점검 재적용을 브라우저에서 확인한다.
2. UI 변경 후 서버를 재시작하고 `/download-review/`에서 정적 파일 `?v=28`이 로드되는지 확인한다.
3. live 테스트가 끝나면 download-review 작업 시작 시간 제한을 운영 기준 `20:00-07:00`으로 되돌린다.

## 기본 검증 명령

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py migrate --database=workflow --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```
