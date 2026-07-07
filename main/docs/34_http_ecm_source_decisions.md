# HTTP 직접연동 ECM Source 도입 — 결정 기록(ADR)

Destiny ECM 산출물 다운로드를 **Playwright + 네이티브 클라이언트 + pywinauto 팝업** 방식에서
**서버측 HTTP 직접 호출(`requests`)** 방식으로 교체하기 위한 결정 추적 문서다.

- 근거 문서: `ECM-API-SHARE.md`(Destiny ECM 직접 연동 구현 가이드, 서버측 파이썬 `requests` 구현).
- 갈아끼우는 자리: `main/views/review/artifact_source.py` 의 새 `ArtifactSource` 구현
  (`HttpEcmArtifactSource`). 심(seam) 위쪽(워커·검증·점검·상태전이)은 불변. 상세: `33_artifact_source_boundary.md`.
- 상태 범례: ✅확정 / 🔶전제 확인중 / ❓미결(추가 답변 필요) / ⏸보류.

---

## 아키텍처 대전제 (결정 6·9·10의 기반)

**이 방식은 "브라우저 → ECM 직접"이 아니라 "서버 → ECM 직접"이다.**

- 공유 코드는 서버측 `requests.Session`이다(브라우저 JS 아님). 문서에 "브라우저/로컬 에이전트 없이 **서버 코드에서** 직접 호출"로 명시.
- 점검 엔진(`gscert_review_core/engine.py`)은 서버측 파이썬이며 xlsx/docx를 **서버 디스크에서** 열어 규칙을 돌린다. 따라서 **파일은 반드시 서버 디스크에 떨어져야 한다.**
- 브라우저 직접 다운로드는 (a) 점검 불가(다시 서버 업로드 필요), (b) CORS 차단, (c) ECM 자격증명 노출로 불가.

```
[기존] 워커 → Playwright + 네이티브 클라이언트 + pywinauto 팝업 → 서버 디스크
[신규] 워커 → requests(HTTP 직접)                              → 서버 디스크
       ↓ (이 아래는 동일)
       검증 → 점검(engine.py) → 결과를 웹 UI로 표시
```

**바뀌는 것:** "파일을 서버에 어떻게 올리는가"(fetch 어댑터)뿐.
**사라지는 것:** Playwright, 네이티브 DestinyECM 클라이언트, pywinauto 팝업, 덮어쓰기 팝업 문제, 에이전트 전용 PC 제약, 단일 에이전트 락의 필요성.
**남는 것:** 로컬 폴더 저장(점검이 읽음), 워커(백그라운드 잡), 검증/보관/점검/상태전이.

---

## 결정 목록

### 결정 1 — 자격증명 저장 방식 ✅
**결정:** 환경변수 방식 채택(`env.ps1.example`에 항목 추가). 코드/DB에 평문 미저장.
**계정 구조:** 총 2개 계정 운영.
- 상암·영남: 같은 서버(210.96.71.85) + **공유 계정 1개**.
- 분당: 서버(210.104.181.10) + **별도 계정 1개**.

**변수명(기존 `ECM_BASE_URL` / `ECM_BASE_URL_BUNDANG` 관례에 맞춤):**
- 상암·영남 공유: `ECM_USERNAME` / `ECM_PASSWORD`
- 분당: `ECM_USERNAME_BUNDANG` / `ECM_PASSWORD_BUNDANG`

`ecm_download_review_centers.py`의 센터 정의에 `username_setting`/`password_setting`을 추가해
base_url과 동일한 방식으로 센터→자격증명을 해석한다(상암·영남은 같은 설정 키를 가리켜 계정 공유를 표현).

### 결정 2 — 세션 수명 관리 ✅
**결정:** job 단위 로그인(`open()`에서 1회, job 내 프로젝트 재사용, `close()`에서 폐기) + 세션 만료(401/세션끊김) 감지 시 1회 자동 재로그인.

### 결정 3 — root OID 설정 위치 ✅
**용어:** OID = Destiny ECM이 모든 폴더/문서에 붙이는 내부 고유 식별자. root OID = 트리 탐색 시작점 폴더의 OID.
분당 `C_ROOT`, 상암 `1PQSYcuFhzv`, 영남 `1EBnGfHdFwe`.
**결정:** `main/views/review/ecm_download_review_centers.py`의 각 센터 정의 dict에 `root_oid`(+ 필요 시 `ecm_root_oid_setting`) 추가 — base_url 옆에 두어 응집.
**남은 확인:** root OID 값이 문서와 일치하는지 실서버 접속 시 실측(구현 후 검증 단계).

### 결정 4 — 프로젝트 식별자 매핑 ✅
**결정:** 문서의 `test_no` 기반 매칭 채택(`cert_no` 금지). zero-padding 양쪽 매칭(`GS-A-23-0336` ↔ `GS-A-23-336`, 뒤 숫자 경계). 연도는 `cert_date` 우선, 없으면 `test_no`의 `-YY-` → `20YY`.
**실측 확인:** `project.project_number`가 `test_no` 포맷과 동일함을 코드/테스트 전반에서 확인 —
`TTA-26-00727`, `TTA-26-00001`, `GS-A-23-0336` 형태(예: `main/tests.py`에서 CSV 파싱 후
`project_number == "TTA-26-00001"` 단언). `cert_no`(`24-0052`) 형식이 아님. **매핑 리스크 해소.**

### 결정 5 — 후보 폴더 선택 정책 ✅
**결정:** 문서 점수제 채택(완료 50 > 종료 45 > 재계약 35 > 계약 25 > 신청 15 > 시험대기 5, 취소 −50, 복사본 −20).
**주의:** 현 Playwright 탐색 결과와 동일한지는 실측/골든 비교로 확인.

### 결정 6 — 디스크 레이아웃 재현 ✅ (전제 정정 완료)
**정정:** 로컬 폴더 저장은 사라지지 않는다(점검이 서버 디스크를 읽음). 사라지는 것은 팝업/저장대화상자 조작뿐.
**결정:** **기존 과정을 그대로 유지한다** — 폴더 생성 → (HTTP) 다운로드 → 저장소 복사 → 원본 삭제.
HTTP source는 기존 Playwright가 만드는 `AGENT_DOWNLOAD_BASE_DIR/<NFC project_number>/…` 폴더 구조를
동일하게 재현하는 것까지만 책임지고, 그 이후(복사·삭제·검증·점검)는 워커의 기존 흐름을 탄다.
**재현 규격(코드에서 확정 — `ecm_agent_popup._try_download_once`):**
```
AGENT_DOWNLOAD_BASE_DIR/
  <NFC project_number>/          ← download_dir(프로젝트 루트, FetchResult.download_dir)
    <NFC relative_path[0]>/       ← ECM 폴더 트리의 프로젝트 기준 상대경로
      <NFC relative_path[1]>/
        ...files...               ← target_dir
```
- `segments = [NFC(project_number), *NFC(relative_path)]`, 모든 경로/파일명 **NFC 정규화**(Windows 폴더는 NFC).
- HTTP 방식은 재귀 `folder_contents`/`children` 순회에서 각 폴더의 프로젝트 기준 경로가 곧 `relative_path` →
  파일을 `base/<project_number>/<relative_path>/`에 기록하면 기존과 동일 구조가 나온다(1:1 매핑).
- `downloaded_folder_count` = 파일이 실제 있던 폴더 수. `on_progress(relative_path, doc_count)`는 폴더별 호출.

### 결정 7 — DRM 파일 처리 ✅
**결정:** DRM 처리 없음. `drmStatus`는 무시하고 일반 파일과 동일하게 다운로드한다(GS 산출물에 DRM이 걸리지 않음).

### 결정 8 — 다운로드 무결성 검증 ✅
**결정:** 도입한다. 각 파일 다운로드 직후 검증:
- 매직바이트 확인(zip/xlsx/docx/pptx=`PK`, PDF=`%PDF`) — 확장자와 부합하는지.
- API가 준 `fileSize`와 실제 다운로드 바이트 크기 대조(잘림/빈 응답 탐지).
- 검증 실패 시 1회 재다운로드 후에도 실패하면 해당 프로젝트 fetch를 실패로 처리(FetchResult.error_step="무결성 검증").

### 결정 9 — 워커 존치 / 동시성 ✅ (전제 정정 완료)
**정정:** 워커는 여전히 필요(다운로드+점검이 수 분 걸리는 무거운 백그라운드 작업). 없어지는 건 "에이전트 전용 PC" 제약.
**결정:** 단일 워커 유지. 동시 요청은 대기열로. **이번 작업의 목표는 다운로드 속도 향상뿐이고 나머지 프로세스(잡 큐/상태/취소/로그/순차 처리)는 그대로 둔다.** HTTP source는 락 없음(어댑터 capability로 선언). 폴더 병렬 다운로드 등 추가 최적화는 후순위.

### 결정 10 — 사전정리(`_clear_project_download_dir`) ✅
결정 6이 "기존 과정 동일"로 확정됨에 따라 **그대로 유지한다.** 덮어쓰기 팝업 문제는 HTTP에서 소멸하지만,
재실행 시 이전 잔여 파일 정리 목적은 유효하므로 워커의 기존 공통 단계로 남긴다.

### 결정 11 — source 이름 & 폴백 전략 ✅
**결정:** 새 이름 `ecm-http` 신규 추가. 기존 `ecm`(Playwright)는 삭제하지 않고 폴백 유지. 안정화 후 `DOWNLOAD_REVIEW_SOURCE` 기본값을 `ecm-http`로 전환.

### 결정 12 — 의존성 & 검증 환경 ✅
**의존성:** HTTP 방식은 `requests`만 필요(Playwright/pywinauto 불필요). 추가 위치: `requirements-automation.txt`.
**검증 환경:** **(12b) 채택** — 실서버 접속이 필요한 실측·통합테스트는 Claude가 명령/스크립트를 만들어 제공하고,
사용자가 자신의 PC에서 직접 실행 후 결과를 공유한다(Claude의 명령 샌드박스는 외부 네트워크 egress가 막혀 210.x 접속 불가).

---

## 진행 순서

- [x] 결정 1~12 전부 확정(위 목록 모두 ✅).
- [x] 결정 4·6 실측 확인(project_number == test_no, 레이아웃 규격 코드 확정).

**구현 단계 — 2026-07-07 코드 착수 완료(실서버 실측 검증만 남음):**
1. [x] 설정: `ecm_download_review_centers.py`에 센터별 `default_ecm_root_oid`·`ecm_root_oid_setting`·
   `username_setting`·`password_setting` 추가 + `ecm_root_oid()`/`ecm_credentials()` 접근자.
   `settings.py`/`ui_mock_settings.py`/`env.ps1.example`에 `ECM_USERNAME[_BUNDANG]`/`ECM_PASSWORD[_BUNDANG]`·
   `ECM_ROOT_OID_*`·`ECM_BASE_URL_BUNDANG` 추가.
2. [x] HTTP 클라이언트 모듈 `main/views/review/ecm_http_client.py`(`DestinyECM` 이식 + 세션만료 1회 재로그인,
   `build_client(center)` 팩토리). 의존성 `requests`.
3. [x] `HttpEcmArtifactSource`(artifact_source.py) 구현 — lazy 로그인(센터별 세션 재사용), fetch=프로젝트
   탐색→재귀 순회→`base/<NFC project_number>/<NFC relative_path>/`에 다운로드(NFC + 무결성 검증 + 1회 재시도)
   + on_progress/is_canceled, 락 없음. 팩토리에 `ecm-http` 분기 추가(기존 `ecm` 폴백 유지).
4. [x] `requests`를 `requirements-automation.txt`에 추가.
5. [x] 계약 테스트(mock 클라이언트, 네트워크 없음): 레이아웃/NFC/진행보고/무결성실패+재시도/취소/미탐색/팩토리
   + 순수함수(test_no zero-padding·연도·점수·파일수집). `main/tests.py`
   (`HttpEcmArtifactSourceTests`, `EcmHttpClientPureFunctionTests`).
6. [x] 실서버 통합 검증 명령(12b: 사용자 PC 실행용) `manage.py verify_ecm_http` 제공
   (로그인→탐색→개수, `--download` 시 무결성까지).
7. [x] `33_artifact_source_boundary.md`·settings 주석·`env.ps1.example` 문서화, 이 문서 상태 갱신.

**남은 것(실서버 = 사용자 PC, 결정 12b):**
- root OID 실측(결정 3): `verify_ecm_http` 로 각 센터 로그인→탐색 확인.
- 후보 폴더 선택이 현 Playwright 결과와 일치하는지 골든 비교(결정 5).
- `--download` 로 실제 파일 무결성(매직바이트·크기) 통과 확인 후, 워커를 `--source=ecm-http` 로 시범 운영.
- 안정화 후 `DOWNLOAD_REVIEW_SOURCE` 기본값을 `ecm-http` 로 전환(결정 11).

---

## API 계약 요약 (구현 참고 — 원본: `ECM-API-SHARE.md`)

원본 가이드(서버측 파이썬 `requests` 구현)는 저장소 밖(Telegram 공유)에 있다. 실서버에서 이어서 구현할 때
아래 요약만으로도 착수할 수 있도록 핵심 계약을 옮겨 둔다. 세부/전체 코드는 원본 참조.

**서버/root OID (센터 매핑)**

| 센터 | base_url | root OID |
| --- | --- | --- |
| 분당 | `http://210.104.181.10` | `C_ROOT` |
| 상암 | `http://210.96.71.85` | `1PQSYcuFhzv` |
| 영남 | `http://210.96.71.85` | `1EBnGfHdFwe` |

**로그인** — `GET /auth/login/loginView.do` 먼저 → `POST /auth/login/login.do?`
form: `user_id`, `password`(XOR+Base64), `loginType=""`, `autoLogin=false`, `timezone=Asia/Seoul`.
성공 판정: 쿠키 `SESSION_KEY` 존재. (다운로드 `Authorization`에 재사용)
```python
def xor_encrypt(plain, key="akRngkfl"):
    parts = [str(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(plain)]
    return base64.b64encode("z".join(parts).encode()).decode()
```

**하위 폴더** — `POST /folder/folderExt.do?method=getChildren` form `OID=<folderOID>`.
응답: JSON 배열 직접 or `{params:{children:[...]}}`. 필드 `name`, `OID/oid`, `objectType`(폴더=`FO`).

**폴더 내 파일** — `POST /document/documentList.do?method=getDocumentListData`
form 필수: `listDataColumns[DO][0..2]`=OID/objectType/files, `listDataColumns[FL][0..4]`=OID/fileName/storageFileID/fileSize/drmStatus, `pageunit=300`, `OID=<folderOID>`, `folderType=C`, `init=true`.
응답은 중첩 JSON → **전체 재귀 순회**로 `fileName`&`storageFileID` 있는 노드 수집. `storageFileID`로 dedup.

**다운로드** — `POST /servlet/blob?<query>` (`.do` 아님, 본문 빈 문자열).
query 핵심: `Method=get`, `BLOBType=doc`, `FileStatus=N`, `FileSize`, `FileID=storageFileID`, `Mode=save`,
`FileName`, `FileOID`, `FileExt`, `clientType=W`, `localShare=false`, **`encryptionClient=false`**(핵심),
`DownloadAt=webBrowser`, `DownloadTo=localDrive`, `UseHistory=true`, `Browser=unknown`.
headers: `Authorization: Basic base64(SESSION_KEY)`, `User-Agent: DestinyECM`, `Content-Type: application/x-www-form-urlencoded`.

**프로젝트 폴더 탐색** — `test_no`로만 매칭(`cert_no` 금지). 연도(`{YYYY} 시험서비스`) → `GS` 포함 하위 root →
프로젝트 폴더. zero-padding 양쪽 매칭(`GS-A-23-0336`↔`GS-A-23-336`, 뒤 숫자 경계). 후보 다수면 점수제(완료>종료>…, 취소/복사본 감점). (결정 4·5)

**무결성 검증(결정 8)** — 다운로드 후 매직바이트(zip/xlsx/docx/pptx=`PK`, PDF=`%PDF`) + `fileSize` 대조.

---

## 이어받기 (실서버) 시작 지점

**상태:** 결정 1~12 전부 확정(위 목록 ✅). **코드 착수 완료(2026-07-07)** — 위 "구현 단계" 1~7 구현·단위테스트 통과.
실서버 실측(로그인/탐색/다운로드)만 남음. 아래 순서로 검증하면 된다.

**0) 준비 — 환경변수 (결정 1, 실서버에서만)**
```powershell
# 상암·영남 공유 계정
$env:ECM_USERNAME = "..."; $env:ECM_PASSWORD = "..."
# 분당 계정
$env:ECM_USERNAME_BUNDANG = "..."; $env:ECM_PASSWORD_BUNDANG = "..."
```

**1) 실서버에서 검증할 것 (결정 12=사용자 실행):** 코드는 이미 착수됐으므로, 운영 코드 경로를 그대로 타는
검증 명령으로 프로젝트 1건 확인(샌드박스는 210.x 접속 불가하므로 사용자 PC에서 실행):
```powershell
# 로그인 → 프로젝트 폴더 탐색 → 폴더별 파일 개수(다운로드 없음)
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center sangam --test-no GS-C-24-0003 --date 2024-01-01
# 실제 다운로드 + 무결성 검증까지(임시 폴더)
.\.venv\Scripts\python.exe manage.py verify_ecm_http --center bundang --test-no GS-A-23-0336 --download --limit 3
```

**2) 시범 운영:** 검증 통과 후 워커를 `--source=ecm-http` 로 실행. 심(seam) 위쪽(워커/검증/점검/상태전이)은
불변이라 새 어댑터만 갈아끼운다. 문제 시 `--source=ecm`(Playwright) 즉시 롤백.

**3) 착수 파일 지도:**
- 설정: `main/views/review/ecm_download_review_centers.py`(센터 dict에 root_oid·계정키), `myproject/settings.py`·`ui_mock_settings.py`·`env.ps1.example`.
- 신규: `main/views/review/ecm_http_client.py`(DestinyECM 이식), `HttpEcmArtifactSource`(=`main/views/review/artifact_source.py`), 팩토리 `ecm-http` 분기.
- 재현 레이아웃 규격: 이 문서 "결정 6" 참조. 진입점 계약: `33_artifact_source_boundary.md`.
- 테스트: `main/tests.py`(mock 세션, 네트워크 없음). 의존성: `requirements-automation.txt`에 `requests`.
