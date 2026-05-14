# main/views/review

## 역할

Review 영역의 ECM 제출물 자동 점검 Python 코드를 보관한다.

## 파일 규칙

- ECM download-review 기능 파일은 `ecm_` prefix를 붙인다.
- 화면 세트는 `main/templates/review`, `main/static/css/review`, `main/static/scripts/review`, `main/views/review`에 같은 영역명으로 둔다.
- 기존 `playwright_job/`는 URL 복사/기존 WebSocket 작업용이고, 이 폴더는 ECM 제출물 다운로드와 점검 작업용이다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `ecm_download_review_centers.py` | 상암/영남 센터별 DB와 ECM 트리 루트 설정 |
| `ecm_download_review_jobs.py` | 작업 요청, 예약/대기열, polling 응답 직렬화 |
| `ecm_download_review_worker.py` | worker claim, heartbeat, dry-run/live 처리 |
| `ecm_reference_db.py` | 센터별 `ecmlist*.db` 조회와 점검 결과 write-back |
| `ecm_download.py` | ECM 웹페이지1 Playwright 자동화 |
| `ecm_selectors.py` | ECM 웹페이지1 selector 상수 |
| `ecm_agent_popup.py` | Windows ECM Agent 팝업 자동화 |
| `ecm_download_verify.py` | 다운로드 파일 존재/개수/0 byte 검증 |
