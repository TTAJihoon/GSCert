# 설치 패키지 관리

## 목적

개발, 운영 서버, Windows agent 자동화에 필요한 Python 패키지를 분리해서 추적한다.

## 기준

- Python: 운영 서버에 설치된 안정 버전을 기준으로 별도 확인한다.
- Django: `>=5.2,<5.3`으로 고정한다.
- 서버 공통 의존성: `requirements.txt`
- ECM/Windows agent 자동화 의존성: `requirements-automation.txt`
- FAISS/임베딩/형태소 분석 의존성: `requirements-search.txt`

## 파일별 역할

### `requirements.txt`

운영 서버와 일반 Django 기능에 필요한 공통 패키지를 담는다. Playwright, pywinauto, pywin32처럼 Windows agent PC에만 필요한 패키지는 넣지 않는다.

### `requirements-automation.txt`

실제 ECM 다운로드 자동화와 Windows agent 팝업 제어에 필요한 패키지를 담는다.

```powershell
pip install -r requirements-automation.txt
playwright install chromium
```

### `requirements-search.txt`

FAISS 인덱스 생성, 임베딩 검색, 형태소 분석처럼 검색/유사도 기능에 필요한 무거운 패키지를 담는다. 웹서버 기본 실행에는 설치하지 않고, 검색/임베딩 기능을 실행하는 환경에서만 추가 설치한다.

```powershell
pip install -r requirements-search.txt
```

## 설치/갱신 원칙

새 패키지를 설치할 때는 아래 내용을 이 문서에 추가한다.

1. 패키지명
2. 설치 이유
3. 사용 위치
4. 어느 requirements 파일에 넣었는지
5. 설치 후 검증 명령과 결과

## 현재 주요 패키지

| 파일 | 패키지 | 용도 |
| --- | --- | --- |
| `requirements.txt` | Django 5.2 계열 | Django 웹 애플리케이션 |
| `requirements.txt` | channels, daphne | WebSocket/ASGI 지원 |
| `requirements.txt` | openpyxl, pandas, lxml, pdfminer.six, PyMuPDF, python-pptx | 문서/파일 파싱 |
| `requirements.txt` | beautifulsoup4, bleach, tinycss2 | HTML 파싱 및 sanitizer |
| `requirements.txt` | openai, google-genai, python-dotenv | AI API 및 환경변수 |
| `requirements-automation.txt` | playwright | ECM 웹페이지1 자동화 |
| `requirements-automation.txt` | pywinauto, pywin32 | Windows 폴더 선택 팝업, 전송현황, 시스템 알림 제어 |
| `requirements-search.txt` | faiss-cpu, sentence-transformers, kiwipiepy | FAISS 인덱스, 임베딩 검색, 형태소 분석 |

## 주의

- Django 6.x 업그레이드는 ECM/Windows agent 자동화 안정화와 분리해서 별도 작업으로 진행한다.
- live worker는 Playwright/pywinauto가 없어도 import 단계에서 실패하지 않아야 한다.
- 자동화 패키지가 없는 환경에서는 `--live` 실행 시 해석 가능한 오류를 남기고 실패해야 한다.
- `requirements-ui.txt`는 실제 API/DB 연동 UI 흐름과 맞지 않아 제거했다. UI 목업도 기본적으로 `requirements.txt` 기준으로 실행한다.
