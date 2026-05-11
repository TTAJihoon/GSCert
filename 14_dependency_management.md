# 설치 패키지 관리

## 목적

개발과 운영에 필요한 Python 패키지를 추적한다.

앞으로 새 패키지를 설치하면 이 문서를 함께 갱신한다.

## 현재 환경

- Python: 3.12.10
- 가상환경: `.venv`
- 패키지 기준: 2026-05-10 현재 `pip freeze`
- 설치 재현 파일: `requirements.txt`

## 설치/갱신 원칙

새 패키지를 설치할 때는 아래 내용을 이 문서에 추가한다.

1. 패키지명
2. 설치 이유
3. 사용 위치
4. 설치 명령
5. 설치 후 `pip freeze` 기준 버전

## 주요 패키지 요약

### 웹서버와 Django

| 패키지 | 현재 버전 | 용도 |
| --- | --- | --- |
| Django | 6.0.5 | Django 웹 애플리케이션 |
| channels | 4.3.2 | WebSocket/ASGI 지원 |
| daphne | 4.2.1 | Channels ASGI 서버 구성 지원 |
| uvicorn | 설치 목록 없음 | 운영 서버 스크립트에서 사용 예정. 서버 환경에는 설치 필요 |

주의:

- 기존 소스 주석은 Django 5.2 기준으로 생성되어 있으나 현재 개발 가상환경에는 Django 6.0.5가 설치되어 있다.
- 운영 서버와 개발 PC의 Django 버전을 맞출지 결정해야 한다.

### 웹페이지 자동화와 Windows 에이전트 제어

| 패키지 | 현재 버전 | 용도 |
| --- | --- | --- |
| playwright | 1.59.0 | 웹페이지1 자동화 |
| pywin32 | 311 | Windows clipboard/Win32 API 사용 |
| pywinauto | 0.6.9 | Windows 폴더 선택 팝업, 전송현황, 시스템 알림 제어 |

### 문서와 파일 파싱

| 패키지 | 현재 버전 | 용도 |
| --- | --- | --- |
| openpyxl | 3.1.5 | Excel 파일 읽기/쓰기 |
| pandas | 3.0.2 | CSV/Excel/DB 데이터 처리 |
| lxml | 6.1.0 | DOCX 내부 XML 파싱 |
| pdfminer.six | 20260107 | PDF 텍스트 추출 |
| PyMuPDF | 1.27.2.3 | PDF/문서 처리 보조 |
| python-pptx | 1.0.2 | PPTX 텍스트 추출 |
| beautifulsoup4 | 4.14.3 | HTML 파싱 |
| bleach | 6.3.0 | HTML sanitizer |
| tinycss2 | 1.5.1 | bleach CSS sanitizer 의존성 |

### AI, 임베딩, 유사도 검색

| 패키지 | 현재 버전 | 용도 |
| --- | --- | --- |
| openai | 2.36.0 | OpenAI API 호출 |
| python-dotenv | 1.2.2 | 환경변수 로딩 |
| faiss-cpu | 1.13.2 | FAISS 벡터 검색 |
| sentence-transformers | 5.4.1 | 문장 임베딩 |
| langchain-community | 0.4.1 | LangChain community vector store |
| langchain-huggingface | 1.2.2 | HuggingFace embedding 연동 |
| kiwipiepy | 0.23.1 | 한국어 형태소 처리 |
| fuzzywuzzy | 0.18.0 | 문자열 유사도 |
| python-Levenshtein | 0.27.3 | fuzzywuzzy 성능 보조 |

### 기타 주요 의존성

| 패키지 | 현재 버전 | 용도 |
| --- | --- | --- |
| numpy | 2.4.4 | 수치 연산 |
| scikit-learn | 1.8.0 | 유사도/머신러닝 보조 |
| torch | 2.11.0 | sentence-transformers 의존성 |
| transformers | 5.8.0 | sentence-transformers 의존성 |
| requests | 2.33.1 | HTTP 요청 |
| SQLAlchemy | 2.0.49 | LangChain/DB 관련 의존성 |

## 최근 설치 기록

### 2026-05-10

설치/확인된 주요 패키지:

```powershell
pip install Django channels daphne playwright pywin32 openpyxl pandas lxml pdfminer.six beautifulsoup4 bleach fuzzywuzzy python-Levenshtein PyMuPDF python-pptx openai python-dotenv numpy
pip install langchain-community langchain-huggingface faiss-cpu sentence-transformers kiwipiepy pywinauto
pip install tinycss2
```

설치 이유:

- 기존 Django 앱 실행에 필요한 패키지 준비
- 웹페이지1 자동화와 Windows 에이전트 팝업 제어 준비
- 기존 testing/review/certy 기능 import에 필요한 패키지 준비
- `bleach.css_sanitizer` import 시 누락된 `tinycss2` 보완

## 현재 pip freeze

```text
aiohappyeyeballs==2.6.1
aiohttp==3.13.5
aiosignal==1.4.0
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.13.0
asgiref==3.11.1
attrs==26.1.0
autobahn==25.12.2
Automat==25.4.16
beautifulsoup4==4.14.3
bleach==6.3.0
cbor2==6.0.1
certifi==2026.4.22
cffi==2.0.0
channels==4.3.2
charset-normalizer==3.4.7
click==8.3.3
colorama==0.4.6
comtypes==1.4.16
constantly==23.10.4
cryptography==48.0.0
daphne==4.2.1
dataclasses-json==0.6.7
distro==1.9.0
Django==6.0.5
et_xmlfile==2.0.0
faiss-cpu==1.13.2
filelock==3.29.0
frozenlist==1.8.0
fsspec==2026.4.0
fuzzywuzzy==0.18.0
greenlet==3.5.0
h11==0.16.0
hf-xet==1.5.0
httpcore==1.0.9
httpx==0.28.1
httpx-sse==0.4.3
huggingface_hub==1.14.0
hyperlink==21.0.0
idna==3.13
Incremental==24.11.0
Jinja2==3.1.6
jiter==0.14.0
joblib==1.5.3
jsonpatch==1.33
jsonpointer==3.1.1
kiwipiepy==0.23.1
kiwipiepy_model==0.23.0
langchain-classic==1.0.7
langchain-community==0.4.1
langchain-core==1.3.3
langchain-huggingface==1.2.2
langchain-protocol==0.0.15
langchain-text-splitters==1.1.2
langsmith==0.8.3
Levenshtein==0.27.3
lxml==6.1.0
markdown-it-py==4.2.0
MarkupSafe==3.0.3
marshmallow==3.26.2
mdurl==0.1.2
mpmath==1.3.0
msgpack==1.1.2
multidict==6.7.1
mypy_extensions==1.1.0
networkx==3.6.1
numpy==2.4.4
openai==2.36.0
openpyxl==3.1.5
orjson==3.11.9
packaging==26.2
pandas==3.0.2
pdfminer.six==20260107
pillow==12.2.0
playwright==1.59.0
propcache==0.4.1
py-ubjson==0.16.1
pyasn1==0.6.3
pyasn1_modules==0.4.2
pycparser==3.0
pydantic==2.13.4
pydantic-settings==2.14.0
pydantic_core==2.46.4
pyee==13.0.1
Pygments==2.20.0
PyMuPDF==1.27.2.3
pyOpenSSL==26.2.0
python-dateutil==2.9.0.post0
python-dotenv==1.2.2
python-Levenshtein==0.27.3
python-pptx==1.0.2
pywin32==311
pywinauto==0.6.9
PyYAML==6.0.3
RapidFuzz==3.14.5
regex==2026.4.4
requests==2.33.1
requests-toolbelt==1.0.0
rich==15.0.0
safetensors==0.7.0
scikit-learn==1.8.0
scipy==1.17.1
sentence-transformers==5.4.1
service-identity==24.2.0
setuptools==81.0.0
shellingham==1.5.4
six==1.17.0
sniffio==1.3.1
soupsieve==2.8.3
SQLAlchemy==2.0.49
sqlparse==0.5.5
sympy==1.14.0
tenacity==9.1.4
threadpoolctl==3.6.0
tinycss2==1.5.1
tokenizers==0.22.2
torch==2.11.0
tqdm==4.67.3
transformers==5.8.0
Twisted==25.5.0
txaio==25.12.2
typer==0.25.1
typing-inspect==0.9.0
typing-inspection==0.4.2
typing_extensions==4.15.0
tzdata==2026.2
ujson==5.12.1
urllib3==2.7.0
uuid_utils==0.14.1
webencodings==0.5.1
xlsxwriter==3.2.9
xxhash==3.7.0
yarl==1.23.0
zope.interface==8.4
zstandard==0.25.0
```

## 추후 정리할 항목

- 운영 서버와 개발 PC의 패키지 버전 일치 여부
- 개발용/운영용 requirements 분리 여부
- Django 버전을 기존 생성 버전인 5.2 계열로 맞출지, 현재 설치된 6.0.5로 유지할지
- uvicorn 설치 여부 확인
