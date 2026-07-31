# GSCert Next Step

## 현재 기준

- 작업 브랜치: `codex-job-runner-persistence`
- 다운로드 점검 화면: `http://127.0.0.1:8000/download-review/`
- 개발 서버 예시:
  ```powershell
  .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings --noreload
  ```
- 운영 기준 프로젝트, PL 매핑, 점검규칙, 수동 적합 메모는 공유 PostgreSQL `reference` DB를 사용한다.
- 작업 상태, 프로젝트 처리 상태, 규칙 결과, 로그, lock, 유사 분석 작업은 서버 로컬 `workflow.db`에 저장한다.
- 점검 규칙 1~18번은 실제 규칙으로 구현되어 있으며, 운영 반영은 `seed_download_review_rules --only-real --enable --update-existing` 기준으로 한다.
- Windows 로컬 앱 배포 ZIP은 `GET /api/local-review/app/download/`에서 `C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard` 폴더를 스트리밍한다.

## 최신 완료 요약

완료된 변경의 상세 목록은 `14_completed_download_review_changes.md`를 본다. 현재 운영자가 바로 알아야 할 완료 항목은 다음과 같다.

- 수동 적합 처리 메모는 `inspection_manual_override` 테이블에 저장하며, 이 테이블은 PostgreSQL `reference` DB 소속이다.
- 수동 적합 결과는 다음 재점검에서도 센터/프로젝트번호/규칙코드/세부항목 키 기준으로 재적용되고, UI에서는 해당 세부항목만 보라색 정상 배지와 메모로 표시된다. 기존 규칙 단위 override(`sub_check_key=""`)는 호환용으로 규칙 전체에 적용된다.
- 테스트케이스처럼 선행 하위검사가 실패해 후속 하위검사를 실제 수행할 수 없는 경우에도 후속 세부항목은 부적합 placeholder로 표시해 결과 세부항목 수를 유지한다.
- PostgreSQL `inspection_manual_override` 테이블이 아직 없을 때도 SQLSTATE `42P01` 또는 한국어 `릴레이션이 없습니다` 오류를 감지해 현재 요청은 로그 fallback으로 처리한다. 단, 운영 지속 저장을 위해 reference migration은 반드시 실행한다.
- 전체 산출물 다운로드는 `GET /api/projects/<프로젝트번호>/full-documents-download/?cert_date=...` attachment 응답을 직접 열어, ZIP 전체 생성 완료를 기다리지 않고 다운로드를 시작한다.
- `수정 내용.txt`가 발견되면 결과 모달의 `수정 내용` 버튼이 활성화되고 팝업으로 본문을 표시한다.
- 파일명 개정 버전 dedup, 9-6 버전 파싱 완화, 10번 결함리포트 시트명 공백 무시 비교가 반영되어 있다.
- `프로젝트 선택`, `현재 작업 진행 상황`, `작업 조회` 탭은 클릭해 이동할 때마다 해당 탭 데이터를 다시 조회한다.

## 운영 반영 체크

GitHub 최신 코드를 서버에 받은 뒤 DB와 서비스를 다음 순서로 맞춘다.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.settings
.\.venv\Scripts\python.exe manage.py migrate_manual_overrides_to_reference --settings=myproject.settings
```

수동 적합 처리 API나 화면 변경을 확인하려면 Django 서버 재시작이 필요하다. 워커는 이미 실행 중인 작업이 새 규칙/override 재적용 로직을 즉시 써야 할 때 재시작한다.

## 바로 다음 작업

1. 운영 ECM 프로젝트 1건으로 세부항목 단위 수동 적합 처리 저장, 보라색 정상 배지, 재점검 재적용을 브라우저에서 확인한다.
2. 같은 프로젝트에서 전체 산출물 다운로드 스트리밍, `수정 내용` 팝업, 파일명 개정 버전 dedup을 확인한다.
3. live 테스트가 끝나면 download-review 작업 시작 시간 제한을 운영 기준 `20:00-07:00`으로 되돌린다.

## 기본 검증 명령

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py migrate --database=workflow --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```
