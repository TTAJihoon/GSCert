# GSCert 서버 관리 시스템

## 1. 설치 폴더 생성

PowerShell을 **관리자 권한**으로 실행한 뒤 아래 명령을 실행합니다.

```powershell
New-Item -ItemType Directory -Force -Path "C:\Claude_GSCert"
Set-Location "C:\Claude_GSCert"
```

---

## 2. Git 설치 및 초기 설정

Git이 설치되어 있지 않다면 먼저 설치합니다.

```powershell
# winget으로 Git 설치 (Windows 10 1709 이상)
winget install --id Git.Git -e --source winget
```

설치 후 PowerShell을 **재시작**하고, 사용자 정보를 등록합니다.

```powershell
git config --global user.name  "이름"
git config --global user.email "이메일@example.com"
```

---

## 3. 저장소 복제 (최초 1회)

```powershell
Set-Location "C:\"
git clone https://github.com/TTAJihoon/GSCert.git Claude_GSCert
Set-Location "C:\Claude_GSCert"
```

이후 업데이트가 있을 때는 아래 명령으로 최신 코드를 가져옵니다.

```powershell
Set-Location "C:\Claude_GSCert"
git pull
```

> **주의** `env.ps1` 파일(DB 비밀번호 등 환경변수)은 저장소에 포함되어 있지 않습니다.  
> 별도로 전달받은 `env.ps1`을 `C:\Claude_GSCert\` 에 복사해 두어야 합니다.

---

## 4. 런처 실행

```powershell
Set-Location "C:\Claude_GSCert"
.\launcher.ps1
```

실행하면 아래와 같은 메뉴가 표시됩니다.

```
=======================================
       GSCert 서버 관리 메뉴
=======================================
  1. start_all      - Django 서버 + 워커 함께 시작
  2. start_server   - Django 개발 서버만 시작 (백그라운드)
  3. start_worker   - download_worker만 시작 (백그라운드)
  4. stop_all       - 서버 + 워커 함께 중지
  5. stop_server    - Django 서버만 중지
  6. stop_worker    - download_worker만 중지
  7. status         - 서버/워커 상태 확인
  8. run_ui_mock    - UI 목 서버 실행
  9. collectstatic  - 정적 파일(css/js) 수집 (nginx 반영)
  R. restart        - 서버/워커 재시작
  N. nginx          - nginx 시작/중지/reload
  S. setup          - 초기 환경 설정 (최초 1회 / 새 PC)
  W. weekly 동기화  - ECM xlsx 다운로드 → PostgreSQL reference DB 적재
  G. Google Sheets  - 인증위 시트 → PostgreSQL reference_project 적재
  I. FAISS 임베딩   - reference DB 신규 데이터 증분 임베딩
  0. 종료
=======================================
```

### 메뉴 항목 설명

| 키 | 설명 |
|---|---|
| **S** | **처음 설치 시 반드시 실행.** 가상환경 생성 및 패키지 설치 |
| **1** | 서버 + 워커를 한 번에 시작 (live / dry-run 선택) |
| **2** | Django 서버만 백그라운드로 시작 |
| **3** | 다운로드 워커만 시작 (live / dry-run / headless 선택 가능) |
| **4** | 서버 + 워커 모두 중지 |
| **5** | Django 서버만 중지 |
| **6** | 다운로드 워커만 중지 |
| **7** | 현재 서버/워커 실행 상태 확인 |
| **9** | CSS·JS 변경 사항을 nginx에 반영 |
| **R** | 서버, 워커, 또는 전체를 재시작 |
| **N** | nginx 시작 / 중지 / 설정 재적재(reload) |
| **W** | 인증획득제품 주간 동기화 |
| **G** | 인증위 Google Sheets → PostgreSQL 동기화 |
| **I** | FAISS 유사 시험 검색 인덱스 증분 업데이트 |

### W (weekly 동기화) 상세

실행하면 두 가지 모드를 선택합니다.

```
1) 자동 다운로드 후 처리   → EDM 시스템에서 xlsx를 직접 다운로드
2) 수동 파일 지정          → 이미 받아 둔 xlsx 파일(또는 폴더) 경로 입력
```

모드 2에서 **폴더 경로**를 입력하면 해당 폴더 안에서 `인증획득제품`이 포함된 xlsx 중 날짜가 가장 최신인 파일을 자동으로 선택합니다.

### 처음 설치 순서

```
S → (재시작 후) N → 1
```

1. **S** 를 입력해 가상환경과 패키지를 설치합니다.
2. PowerShell 창을 닫고 다시 열어 `.\launcher.ps1`을 실행합니다.
3. **N** 으로 nginx를 시작합니다.
4. **1** 로 서버와 워커를 시작합니다.
