# 새 PC에서 GSCert 서버 구축 (현재 서버와 동일 동작)

GitHub 클론만으로는 동작하지 않는 항목(자격증명·PostgreSQL 데이터·빌드 산출물)이 있어
아래 순서대로 진행해야 현재 서버와 동일하게 동작한다.

> 클론에 포함된 것: 전체 소스, `gscert_review_core`, `main/data/reference.xlsx`(참조 원본),
> `main/data/reference.db`(구 SQLite 스냅샷), requirements.
> 클론에 **없는** 것: `env.ps1`(비밀번호), PostgreSQL `gscert_reference` DB·데이터,
> FAISS 인덱스(`faiss_bge_m3_ko.idmap.index`).

## 1. PostgreSQL 설치 및 DB 생성 (setup.ps1이 자동화하지 않음)

`reference` 데이터(`sw_data`, 약 9,121행)는 PostgreSQL `gscert_reference` DB를 사용한다.

1. PostgreSQL 설치 (현재 서버와 동일 메이저 버전 권장).
2. DB 생성:
   ```sql
   CREATE DATABASE gscert_reference;
   ```
   기본 계정은 `postgres`를 사용한다(필요 시 별도 계정·권한 구성).

## 2. 자격증명 파일 준비 (`env.ps1`)

```powershell
Copy-Item env.ps1.example env.ps1
# env.ps1 을 열어 REFERENCE_PG_PASSWORD 등 실제 값 입력
```

`env.ps1` 은 `.gitignore` 에 포함되어 커밋되지 않는다(비밀번호 보호).
`start_server.ps1` / `start_worker.ps1` / `launcher.ps1` / `setup.ps1` 이 시작 시 자동 로드한다.

환경변수: `REFERENCE_PG_NAME`, `REFERENCE_PG_USER`, `REFERENCE_PG_PASSWORD`,
`REFERENCE_PG_HOST`, `REFERENCE_PG_PORT`.

## 3. 초기 환경 설정 실행 (`setup.ps1`)

```powershell
# 검색(유사 시험 조회)까지 쓰려면 -InstallSearch, ECM 자동화까지면 -InstallAutomation
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -InstallSearch
```

setup.ps1 이 수행하는 것:
- Python / Git / VC++ / nginx / LibreOffice 설치
- 가상환경 생성 + requirements 설치 (+ 옵션 패키지)
- `collectstatic`
- `migrate` (default) + `migrate --database=workflow`
- **`migrate --database=reference` + `import_reference_db --source-xlsx main/data/reference.xlsx`**
  (1·2단계가 끝나 PostgreSQL 접속이 되는 경우에만 자동 수행. 접속 불가 시 건너뛰고 안내 출력)
- `-InstallSearch` 지정 시 `embed_db`(FAISS 증분 임베딩)까지 수행

PostgreSQL을 setup 이후에 준비했다면, 아래만 수동 실행하면 된다:
```powershell
. .\env.ps1
.\.venv\Scripts\python.exe manage.py migrate --database=reference
.\.venv\Scripts\python.exe manage.py import_reference_db --source-xlsx main\data\reference.xlsx
```

## 4. FAISS 임베딩 (유사 시험 조회용)

검색 인덱스는 빌드 산출물이라 git에 없다. reference 데이터 적재 후 1회 생성한다.
```powershell
.\.venv\Scripts\python.exe manage.py embed_db        # PostgreSQL 소스, 증분
```
또는 launcher.ps1 의 `f` 메뉴 사용. 이후 신규 데이터는 `weekly`(launcher `W`) → `embed_db` 순으로 증분 갱신.

## 5. 서버 시작

launcher.ps1 → `1. start_all` (또는 `start_server` / `start_worker`).

## 확인 체크리스트

- [ ] PostgreSQL `gscert_reference` DB 존재 + `sw_data` 행 수 정상 (`import_reference_db` 출력 확인)
- [ ] `env.ps1` 존재 및 비밀번호 정확
- [ ] `/api/reference/search/?q=...` 응답 정상 (reference 검색)
- [ ] 시험 이력 조회 / 유사 시험 조회 동작 (PostgreSQL + FAISS)
- [ ] nginx 기동, static 제공

## 참고

- 점검 엔진 공유 코어(`gscert_review_core/`)는 저장소 루트에 있으며 Django가 루트에서 실행되므로
  별도 설치 없이 import된다.
- 단계별 리팩터링 진행 상황은 [REFACTORING_PHASES.md](REFACTORING_PHASES.md) 참고.
