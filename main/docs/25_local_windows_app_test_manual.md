# 로컬 Windows ECM 점검 앱 테스트 매뉴얼

## 현재 결론

현재 Windows 프로그램으로 테스트할 수 있는 범위는 다음과 같다.

- 로컬 폴더 선택
- 폴더명 또는 파일명에서 프로젝트 번호 자동 추정
- 서버 health API 연결 확인
- 서버 프로젝트 기준정보 API 조회
- 로컬 파일 목록 스캔 및 표시
- PyInstaller 기반 `.exe` 패키징 시도

아직 테스트할 수 없는 범위는 다음과 같다.

- 기존 ECM 점검 규칙 전체 실행
- 규칙별 점검 결과 화면 표시
- 점검 결과 상세 팝업 표시
- 점검 결과 Excel/HTML 내보내기
- 로컬 실행 결과 서버 업로드

즉, 지금 앱은 “실제 점검 엔진 연결 전 단계의 데스크톱 앱 골격”이다. ECM 점검 테스트는 폴더 선택과 파일 스캔, 서버 기준정보 조회까지 가능하며, 규칙 적용 테스트는 다음 구현 단계에서 가능하다.

## 폴더 구조

로컬 앱은 서버 코드와 분리되어 있다.

```text
local_review_app/
  README.md
  requirements.txt
  run.py
  scripts/
    package_windows.ps1
  gscert_local_review/
    app.py
    api_client.py
    project.py
    scanner.py
  tests/
    test_project.py
```

서버 배포와 데스크톱 앱 배포를 분리하기 위해 `local_review_app/requirements.txt`를 별도로 사용한다.

## 개발 환경 설치

저장소 루트에서 다음 명령을 실행한다.

```powershell
cd local_review_app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

이미 서버용 `.venv`가 있어도 로컬 앱은 별도 가상환경을 사용하는 것을 권장한다. PySide6와 PyInstaller는 데스크톱 앱 전용 의존성이기 때문이다.

## 서버 실행

앱에서 기준정보를 조회하려면 Django 서버가 먼저 실행되어 있어야 한다.

개발 PC에서 테스트할 때는 저장소 루트에서 다음 명령을 실행한다.

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings --noreload
```

서버가 실행되면 브라우저 또는 PowerShell에서 health API를 확인한다.

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/local-review/health/" -Method Get
```

정상 응답이면 `ok` 값이 `true`로 표시된다.

## 앱 실행

별도 PowerShell 창에서 다음 명령을 실행한다.

```powershell
cd local_review_app
.\.venv\Scripts\python.exe run.py
```

앱이 실행되면 기본 서버 URL은 다음 값으로 표시된다.

```text
http://127.0.0.1:8000
```

외부 서버를 대상으로 테스트할 때는 이 값을 실제 서버 주소로 변경한다.

예시는 다음과 같다.

```text
http://210.96.71.241:8000
```

실제 운영 포트가 다르면 서버 배포 포트에 맞춰 수정한다.

## 앱 화면 테스트 순서

1. `연결 확인` 버튼을 클릭한다.
2. 서버 연결 정상 메시지를 확인한다.
3. `폴더 선택` 버튼을 클릭한다.
4. ECM에서 내려받은 제출물 폴더를 선택한다.
5. 프로젝트 번호가 자동으로 입력되는지 확인한다.
6. 자동 입력이 안 되면 프로젝트 번호를 직접 입력한다.
7. 센터를 `상암` 또는 `영남`으로 선택한다.
8. `기준정보 조회` 버튼을 클릭한다.
9. 회사명, 제품명, PL, WD, 인증일이 표시되는지 확인한다.
10. `파일 스캔` 버튼을 클릭한다.
11. 파일 목록, 상대 경로, 확장자, 크기 값이 표시되는지 확인한다.

## 프로젝트 번호 자동 추정 기준

현재 프로젝트 번호는 다음 패턴으로 찾는다.

```text
영문 2~5자리-숫자 2자리-숫자 5자리
```

예시는 다음과 같다.

```text
TTA-26-00727
GS-26-00386
```

앱은 선택한 폴더명과 바로 아래 파일명에서 프로젝트 번호를 찾는다. 찾은 값이 있으면 프로젝트 번호 입력칸에 자동으로 채운다.

## 폴더 스캔 기준

앱은 선택한 폴더의 모든 하위 파일을 재귀적으로 스캔한다.

표시 항목은 다음과 같다.

| 항목 | 설명 |
| --- | --- |
| 파일명 | 파일 이름 |
| 상대 경로 | 선택한 폴더 기준 상대 경로 |
| 확장자 | 파일 확장자 |
| 크기(bytes) | 파일 크기 |

파일 정렬은 상위 폴더 파일을 먼저 보여주고, 그다음 하위 폴더 파일을 보여준다.

## `.exe` 패키징

로컬 앱 폴더에서 다음 명령을 실행한다.

```powershell
cd local_review_app
.\scripts\package_windows.ps1
```

기본적으로 다음 Python을 사용한다.

```text
local_review_app\.venv\Scripts\python.exe
```

다른 Python을 사용하려면 `-Python` 인자를 지정한다.

```powershell
.\scripts\package_windows.ps1 -Python "C:\Path\To\python.exe"
```

빌드 결과는 다음 폴더에 생성된다.

```text
local_review_app/dist/GSCertLocalReview/
```

생성된 실행 파일은 다음 위치에 있다.

```text
local_review_app/dist/GSCertLocalReview/GSCertLocalReview.exe
```

## 테스트 데이터 준비

현재 앱 단계에서는 실제 ECM 제출물 전체가 아니어도 테스트할 수 있다.

테스트 폴더 예시는 다음과 같다.

```text
TTA-26-00727_test/
  TTA-26-00727 제출물.zip
  rawdata.zip
  시험기록서.pdf
```

위 폴더를 선택하면 프로젝트 번호 `TTA-26-00727`이 자동 입력되어야 한다.

## 현재 제한사항

현재 앱은 기존 점검 규칙 엔진을 아직 실행하지 않는다.

따라서 다음 버튼 또는 화면은 아직 없다.

- `점검 수행`
- 규칙별 점검 결과
- 결과 상세 팝업
- 점검 결과 저장/내보내기

다음 구현 단계에서 기존 `main/views/review/ecm_download_review_inspection.py`의 규칙 실행 로직을 로컬 runner에서 호출하도록 공용 경계를 정리해야 한다.

## 문제 해결

### 서버 연결이 실패하는 경우

확인할 항목:

- Django 서버가 실행 중인지 확인한다.
- 앱의 서버 URL이 맞는지 확인한다.
- 서버 방화벽에서 API 포트가 열려 있는지 확인한다.
- 외부 서버 테스트라면 PC에서 해당 서버 주소로 접속 가능한지 확인한다.

### 프로젝트 기준정보 조회가 실패하는 경우

확인할 항목:

- 프로젝트 번호가 정확한지 확인한다.
- 센터가 상암/영남 중 올바르게 선택되어 있는지 확인한다.
- 서버의 기준정보 DB에 해당 프로젝트가 있는지 확인한다.
- 현재는 PostgreSQL이 아니라 기존 SQLite 기준정보 DB를 조회한다는 점을 확인한다.

### 앱 실행 시 PySide6 오류가 나는 경우

다음 명령으로 로컬 앱 의존성을 다시 설치한다.

```powershell
cd local_review_app
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### `.exe` 실행 파일이 만들어지지 않는 경우

확인할 항목:

- `pyinstaller`가 설치되어 있는지 확인한다.
- PowerShell 실행 정책 때문에 스크립트 실행이 막히는지 확인한다.
- 백신 프로그램이 빌드 결과물을 차단하는지 확인한다.
- `local_review_app/build/`, `local_review_app/dist/` 폴더를 삭제 후 다시 빌드한다.

## 다음 구현 체크리스트

1. 로컬 runner 모듈을 추가한다.
2. 기존 점검 엔진이 Django ORM 의존 없이 실행될 수 있는 경계를 분리한다.
3. 로컬 파일 스캔 결과를 기존 `verify_result`와 호환되는 형태로 변환한다.
4. 규칙별 결과를 앱 테이블에 표시한다.
5. 상세 팝업을 연결한다.
6. 결과 파일 저장 기능을 추가한다.
7. PyInstaller 빌드 결과를 실제 Windows PC에서 실행 검증한다.
