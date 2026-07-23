# GSCert Next Step

이 문서는 누적 이력 문서가 아니라 다른 PC에서 바로 이어받기 위한 최신 인수인계 문서다. 전체 목차는 `main/docs/01_manual_index.md`를 먼저 본다.

## 현재 기준

- 작업 브랜치: `codex-job-runner-persistence`
- 2026-07-23 기준 원격 변경은 pull 완료했다.
- 문서 정리 후 루트 `main/docs`에는 현재 사용하는 문서만 남기고, 과거 설계/진행 로그는 `main/docs/archive/2026-07-doc-cleanup/`로 이동했다.
- 현재 사용하는 번호 문서는 `00_next_step.md`부터 `13_db_schema.md`까지 연속 번호로 정리했다.
- 다운로드 검토 페이지: `http://127.0.0.1:8000/download-review/`
- 개발 서버 실행 예시: `.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- 테스트용 작업 시작 가능 시간: 현재 `00:00-24:00`
- 운영 복원 기준 시간: `20:00-07:00`
- 운영 복원 마커: `TODO(TEST_ONLY_DOWNLOAD_REVIEW_TIME_WINDOW)`

## 최신 구조 요약

### ECM 다운로드

- download-review는 194 서버가 `ecm-http` source로 분당·상암·영남 세 센터를 모두 처리하는 구조가 기준이다.
- 241 서버는 download-review에서 제외하고 모든 센터 요청을 194로 넘기는 경로로 본다.
- `ecm-http`는 서버측 HTTP 직접 호출(`requests`)로 ECM에 접속한다.
- 기존 Playwright 기반 `ecm` source는 폴백으로 남아 있다.
- 자세한 결정과 검증 절차는 `12_http_ecm_source_decisions.md`와 `11_artifact_source_boundary.md`를 본다.

### DB와 규칙

- `reference` PostgreSQL: 공유 기준정보, `reference_project`, `reference_center_pl`, `sw_data`, `inspection_rule`.
- `workflow` SQLite: 서버 로컬 작업, 프로젝트 처리 상태, `inspection_result`, 로그, lock.
- 점검규칙은 1~18번 실제 규칙이 구현되어 있고 `seed_download_review_rules --only-real --enable --update-existing` 기준으로 반영한다.
- 웹과 Windows 앱은 `inspection_rule` 규칙 bundle과 `gscert_review_core.engine` 공용 실행 코드를 함께 사용한다.
- 점검 결과의 기대값/실제값/메시지 표시는 `gscert_review_core/result_display.py`의 공통 표시 API를 사용한다.
- 7번 시험계획서의 9-12 `<세부사양>` 표 비교는 셀의 공백/줄바꿈을 제거한 뒤 비교한다. 실제 내용이 다르면 기존처럼 셀 위치와 양쪽 값을 실제값에 표시한다.
- 12번 RawData 보안 폴더는 하위 폴더 없이 txt 안내 파일만 있는 경우 예외적으로 통과한다.

### Download-review UI

- 상단 화면 탭 오른쪽에 `윈도우 프로그램 다운로드` 버튼을 추가했다.
- 버튼은 `GET /api/local-review/app/download/`로 연결되며, 서버의 `C:\Claude_GSCert\local_review_app\dist\GSCertLocalReviewDashboard` 폴더를 `GSCertLocalReviewDashboard.zip` 스트리밍 응답으로 내려준다.
- 규칙별 점검 결과 팝업은 상단 요약 카드와 고정 헤더 테이블을 사용하는 형태로 정리했다.
- 팝업의 기본 폭은 1400px이고, 작은 화면에서는 화면 폭 안에 맞춰 줄어든다.
- 팝업 창은 사용자가 크기를 조절할 수 있고, 내용이 넘치면 본문과 규칙 결과 테이블에 스크롤이 생긴다.
- 팝업 우측 상단 다운로드 버튼은 현재 팝업 내용을 그대로 HTML 파일로 저장한다. 전체/선택 엑셀 다운로드 기능은 기존대로 유지한다.
- 센터 선택은 프로젝트 선택 탭 안에서만 한다. 현재 작업 진행 상황과 작업 조회는 서버 큐 기준으로 모든 센터 작업을 누적 표시하는 전역 작업 화면으로 본다.
- 프로젝트 선택 필터는 한 줄 필터바로 표시하고 `조회` 버튼을 눌렀을 때 적용한다. 필터 입력 중 Enter를 눌러도 `조회` 버튼 클릭과 같은 동작을 한다. 초기/센터 전환/DB 새로고침 기본값은 전체 조회이며, 프로젝트번호/회사명/제품명/시험PL 필터는 입력값이 각 항목에 포함되는 결과를 표시한다.
- 검증: `node --check main\static\scripts\review\ecm_download_review.js`, `manage.py check --settings=myproject.ui_mock_settings`, 작업 목록 센터 누적/명시 필터 테스트 2건, `git diff --check`, 로컬 `/download-review/` 로드 및 `/api/jobs/?status=all&limit=50` 센터 미주입 확인을 완료했다. `DownloadReviewJobsApiTests` 전체 실행 시 기존 규칙/샘플 산출물 기대값 관련 4건 실패가 남아 있다.

### Windows 로컬 앱

- 로컬 앱은 서버 API로 프로젝트 기준정보와 규칙 bundle을 가져온다.
- 로컬 파일/폴더 스캔 결과를 공용 엔진에 넘겨 웹과 같은 규칙 기준으로 점검한다.
- 서버 DB 저장과 산출물 캡처 저장은 하지 않고 화면 결과 표시까지 담당한다.
- 공용 엔진 코드가 바뀌면 이미 배포된 Windows exe에는 자동 반영되지 않는다. 서버 워커는 프로세스 재시작 후 새 코드가 적용되고, 로컬 앱은 재빌드/재배포가 필요하다.

## 바로 다음 작업

1. 실서버에서 `ecm-http` 검증을 이어간다.
   ```powershell
   .\.venv\Scripts\python.exe manage.py verify_ecm_http --center bundang --test-no <시험번호> --download
   .\.venv\Scripts\python.exe manage.py verify_ecm_http --center sangam --test-no <시험번호> --download
   .\.venv\Scripts\python.exe manage.py verify_ecm_http --center yeongnam --test-no <시험번호> --download
   ```
2. 샘플 zip 또는 실제 산출물로 1~18번 전체 PASS 여부를 확인한다. `TTA-26-00835` zip은 9-12/11-4/13-1이 통과하고 14-1 시험기록서 누락만 실패로 재확인했다.
3. 테스트가 끝나면 download-review 시간 제한을 운영 기준인 `20:00-07:00`으로 되돌린다.

## 먼저 읽을 문서

1. `main/docs/01_manual_index.md`
2. `main/docs/03_inspection_rule_manual.md`
3. `main/docs/04_download_review_operations_manual.md`
4. `main/docs/05_developer_change_manual.md`
5. `main/docs/13_db_schema.md`

## 기본 검증 명령

코드나 규칙을 바꾸면 아래를 우선 확인한다.

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

문서만 바꾼 경우에는 `git diff --check`를 실행한다.

## 다른 개발 PC에서 시작

```powershell
git clone https://github.com/TTAJihoon/GSCert.git
cd GSCert
git switch codex-job-runner-persistence
git pull
```

이미 저장소가 있으면:

```powershell
git switch codex-job-runner-persistence
git pull
```

Codex skill을 설치하려면:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force `
  ".\main\docs\codex_skills\gscert-download-review-maintainer" `
  "$env:USERPROFILE\.codex\skills\gscert-download-review-maintainer"
```
