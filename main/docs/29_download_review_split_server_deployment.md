# Download Review Split Server Deployment

> ⚠️ 2026-07-08 갱신: ECM HTTP 직접연동 전환으로 **194 단일화**로 바뀌었다. 194 가 분당·상암·영남
> 세 센터를 모두 처리하고 241 은 download-review 에서 제외(모든 요청을 194 로 포워드)한다. 아래 센터별
> 분리 운영 설명은 레거시(Playwright 시절) 기준이다. 최신 기준은 `00_next_step.md`(2026-07-08) 참고.

## 목적

ECM 제출물 자동 점검을 센터별로 다른 서버에서 실행한다.

| 서버 | 담당 센터 | 역할 |
| --- | --- | --- |
| `210.96.71.194` | 분당 | 메인 진입 페이지, 분당 ECM 접속/다운로드/점검 |
| `210.96.71.241` | 상암, 영남 | 상암/영남 ECM 접속/다운로드/점검 |

사용자는 `http://210.96.71.194/download-review/`로 진입한다. 상암 또는 영남 탭을 클릭하면 `http://210.96.71.241/download-review/?center=sangam|yeongnam`으로 이동한다. 241 서버에서 분당 탭을 클릭하면 다시 194 서버로 이동한다.

## 코드 설정

기본 설정은 `myproject/settings.py`와 `myproject/ui_mock_settings.py`에 들어 있다.

```python
DOWNLOAD_REVIEW_DEFAULT_CENTER_BY_HOST = {
    "210.96.71.194": "bundang",
    "210.96.71.241": "sangam",
}

DOWNLOAD_REVIEW_ALLOWED_CENTERS_BY_HOST = {
    "210.96.71.194": {"bundang"},
    "210.96.71.241": {"sangam", "yeongnam"},
}

DOWNLOAD_REVIEW_CENTER_ROUTES_BY_HOST = {
    "210.96.71.194": {
        "bundang": "",
        "sangam": "http://210.96.71.241/download-review/",
        "yeongnam": "http://210.96.71.241/download-review/",
    },
    "210.96.71.241": {
        "bundang": "http://210.96.71.194/download-review/",
        "sangam": "",
        "yeongnam": "",
    },
}
```

## 동작

- `/download-review/` 렌더링 시 현재 Host를 보고 기본 센터를 결정한다.
- 센터 탭 클릭 시 현재 서버에서 처리하는 센터면 화면 내부에서 목록을 전환한다.
- 다른 서버에서 처리하는 센터면 지정된 URL로 이동하고 `center` query string을 붙인다.
- `/api/projects/`, `/api/jobs/`, `/api/local-review/projects/{project_number}/metadata/`는 현재 서버에서 허용하지 않는 센터 요청을 400으로 거절한다.
- worker는 현재 서버 IP를 기준으로 허용된 센터 작업만 claim한다.

## Worker 강제 설정

서버의 로컬 IP 감지가 기대와 다르면 환경변수로 worker 처리 센터를 강제한다.

194 서버:

```powershell
$env:DOWNLOAD_REVIEW_WORKER_CENTERS = "bundang"
```

241 서버:

```powershell
$env:DOWNLOAD_REVIEW_WORKER_CENTERS = "sangam,yeongnam"
```

## 확인 방법

194 서버:

```text
http://210.96.71.194/download-review/
```

- 기본 활성 탭이 `분당`인지 확인한다.
- `상암`, `영남` 탭 클릭 시 241 서버로 이동하는지 확인한다.
- `GET /api/projects/?center=sangam`이 400을 반환하는지 확인한다.

241 서버:

```text
http://210.96.71.241/download-review/?center=sangam
```

- 상암/영남 탭은 같은 서버 안에서 전환되는지 확인한다.
- 분당 탭 클릭 시 194 서버로 이동하는지 확인한다.
- `GET /api/projects/?center=bundang`이 400을 반환하는지 확인한다.
