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
- 기존 download-review `20:00-07:00` 작업 시작 제한은 제거됐다. 새 작업은 즉시 queued가 되고 legacy scheduled 작업은 migration에서 queued로 전환한다.
- 서버 시간 임시 변경 UI/API/3분 lease와 관리자 권한 Windows 서비스가 구현됐다. 임시 시간 동안 접수된 점검 작업은 `queued` 상태로 유지하고 정상 시각 복구 후 시작한다. 확정 설계와 194 반영 절차는 `15_server_time_control_design.md`와 `04_download_review_operations_manual.md`를 기준으로 한다.
- `/download-review/` 최초 진입 시 접속 클라이언트 IP가 `210.96.0.0/16`이면 상암, `210.104.0.0/16`이면 분당 센터 탭을 기본 선택한다. 명시적인 `?center=` 값은 이 기본값보다 우선한다.

## 최신 완료 요약

완료된 변경의 상세 목록은 `14_completed_download_review_changes.md`를 본다. 현재 운영자가 바로 알아야 할 완료 항목은 다음과 같다.

- Windows 로컬 앱의 HTTPS 번들 인증서를 현재 `gsai.tta.or.kr` 자체 서명 인증서로 교체했다. 패키징 self-check는 인증서 파일과 SSL context까지 확인하며, Tcl/Tk가 없는 빌드 환경에서는 splash만 생략한다.
- 수동 적합 처리 메모는 `inspection_manual_override` 테이블에 저장하며, 이 테이블은 PostgreSQL `reference` DB 소속이다.
- 수동 적합 결과는 다음 재점검에서도 센터/프로젝트번호/규칙코드/세부항목 키 기준으로 재적용되고, UI에서는 정상 배지 스타일에 보라색 테두리와 메모로 표시된다. 기존 규칙 단위 override(`sub_check_key=""`)는 호환용으로 규칙 전체에 적용된다.
- 단, 재점검에서 자동 규칙 자체가 적합을 내면 저장된 수동 적합 메모는 보존하되 결과에는 적용하지 않는다. 이 경우 UI는 보라색 테두리 없이 일반 초록색 정상 배지를 표시한다.
- 테스트케이스처럼 선행 하위검사가 실패해 후속 하위검사를 실제 수행할 수 없는 경우에도 후속 세부항목은 부적합 placeholder로 표시해 결과 세부항목 수를 유지한다.
- PostgreSQL `inspection_manual_override` 테이블이 아직 없을 때도 SQLSTATE `42P01` 또는 한국어 `릴레이션이 없습니다` 오류를 감지해 현재 요청은 로그 fallback으로 처리한다. 단, 운영 지속 저장을 위해 reference migration은 반드시 실행한다.
- 전체 산출물 다운로드는 `GET /api/projects/<프로젝트번호>/full-documents-download/?cert_date=...` attachment 응답을 직접 열어, ZIP 전체 생성 완료를 기다리지 않고 다운로드를 시작한다.
- 규칙별 점검 결과 모달의 `메시지` 열은 원인 요약만 표시하고, `기대값`/`실제값` 상세는 별도 컬럼에만 표시한다. 과거 저장 메시지의 `기대값:`/`실제값:` 줄도 화면에서 숨긴다.
- `전체 산출물 다운로드` 버튼은 Font Awesome 호환성이 높은 `fa-folder` 아이콘을 사용한다.
- 파일명에 `수정`이 포함된 txt 파일이 발견되면 결과 모달의 `수정 내용` 버튼이 활성화되고 팝업으로 본문을 표시한다.
- 시험계획서 `소프트웨어 명` 오른쪽 셀은 등록 제품명의 국문명/영문명 후보 중 하나와 일치하면 적합으로 본다.
- 파일명 개정 버전 dedup, 9-6 버전 파싱 완화, 10번 결함리포트 시트명 공백 무시 비교가 반영되어 있다.
- `프로젝트 선택`, `현재 작업 진행 상황`, `작업 조회` 탭은 클릭해 이동할 때마다 해당 탭 데이터를 다시 조회한다.
- 프로젝트 선택 목록은 화면에 표시되는 인증일자 기준으로 최신 인증일자가 항상 위에 오도록 정렬한다.
- 프로젝트 선택 목록에서 점검결과 `완료` 프로젝트는 체크박스가 비활성화된다. 작업 조회 목록은 전체/상암/분당/영남 탭과 5개 단위 페이지 이동으로 조회한다.
- 작업 조회의 이전/다음 페이지 이동 버튼과 작업 상세 결과의 엑셀 다운로드/결과 필터 버튼 스타일을 정돈했다.
- 프로젝트 선택 목록 컬럼 폭 초기값은 체크/프로젝트번호/인증일자/회사명/제품명/시험PL/점검결과/작업상태/상세 순서로 `43/155/123/x/y/168/101/101/74px` 기준을 사용한다. 회사명과 제품명은 최소 400px이며 남는 폭을 4:6으로 나누고, 사용자는 기존처럼 열 너비를 직접 조정할 수 있다.
- 수동 적합으로 전체 점검결과가 `완료`가 된 프로젝트는 프로젝트 목록/상세/작업 상세 결과의 `완료` 배지도 정상 배지 스타일에 보라색 테두리로 표시한다.
- 프로젝트 선택 탭과 규칙별 점검 결과 팝업에 접이식 도움말을 추가했다.
- 프로젝트 선택 상단의 `ECM 서버 시간 설정`, `선택 엑셀 다운로드`, `PL 배정 목록` 버튼은 축소 폰트 크기, 무테두리, 개별 배경색 기준을 사용한다.

## 운영 반영 체크

GitHub 최신 코드를 서버에 받은 뒤 DB와 서비스를 다음 순서로 맞춘다.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.settings
```

수동 적합 처리 API나 화면 변경을 확인하려면 Django 서버 재시작이 필요하다. 워커는 이미 실행 중인 작업이 새 규칙/override 재적용 로직을 즉시 써야 할 때 재시작한다.

## 바로 다음 작업

1. 194 서버에서 새 로컬 앱 배포 폴더를 다시 빌드해 `C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard` 전체를 교체하고 HTTPS 연결을 확인한다.
2. 운영 ECM 프로젝트 1건으로 세부항목 단위 수동 적합 처리 저장, 보라색 테두리 정상 배지, 재점검 재적용을 브라우저에서 확인한다.
3. 같은 프로젝트에서 전체 산출물 다운로드 스트리밍, `수정 내용` 팝업, 파일명 개정 버전 dedup을 확인한다.
4. 194 서버에 workflow migration과 `GSCertTimeControl` 서비스를 반영한 뒤, 대표 과거 시각으로 W32Time 중지·3분 자동복구·점검 작업 대기·SMB 접근을 live 검증한다.

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
