# 산출물 source 경계 (ECM 분리 / 다른 저장소 연결)

> 추후 ECM 대신 로컬·다른 저장소를 붙이거나, ECM 없이 워커 흐름을 테스트할 때
> **가장 먼저 읽을 문서.** 어디를 건드려야 하는지 한눈에 파악하도록 정리한다.

## 1. 왜 있나

산출물 다운로드가 현재 ECM(Playwright + Windows Agent)에 강결합돼 있다. 추후 저장소가
ECM 이 아닐 수 있으므로, "산출물을 받아오는 부분"만 떼어 새 구현으로 갈아끼울 수 있게
**`ArtifactSource` 경계**를 두었다. 이 경계는 테스트 주입 지점과 동일해서, 로컬 source 가
곧 ECM 없는 fake-live 테스트 더블이 된다.

## 2. 경계 (무엇이 source-specific 인가)

| 구분 | 내용 | 위치 |
|---|---|---|
| **source-specific** (갈아끼우는 부분) | 어떻게 받아오는가 — ECM 탐색/팝업, 로컬 복사 등 | `main/views/review/artifact_source.py` |
| **source-agnostic** (그대로 재사용) | 받은 *로컬 폴더*의 검증→보관→점검→상태 전이→정리 | `ecm_download_review_worker.py` 외 |

핵심 계약 한 줄: **`fetch(project) → 로컬 다운로드 폴더`**. 그 폴더만 만들어 주면 이후
파이프라인(`verify_downloaded_files` → `summarize_files` → `run_download_inspection` → 상태/정리)은
source 를 모른 채 동작한다.

## 3. 계약 (`ArtifactSource`)

`main/views/review/artifact_source.py`

```python
class ArtifactSource(Protocol):
    async def open(self) -> None          # 작업(job) 단위 준비 (예: 브라우저 launch). 1회.
    async def close(self) -> None         # 작업 단위 정리 (예: 브라우저 close). 1회.
    async def fetch(self, project, *, on_progress, is_canceled) -> FetchResult
```

- `FetchResult(success, download_dir, downloaded_folder_count, error_step, error_message)`
- `on_progress(relative_path: list, doc_count: int)` — async. 진행 보고(워커가 `_mark_project` 로 매핑).
- `is_canceled() -> bool` — async. True 면 `fetch` 가 `JobCanceledError` 를 던져 즉시 중단.
- source 는 **Django 모델을 몰라야 한다** — 진행/취소는 콜백으로만 받는다.

### 구현체

- `HttpEcmArtifactSource`(`ecm-http`, **운영 기본**): 서버측 HTTP 직접 호출(`requests`)로 ECM 을 부른다.
  `open`=lazy 로그인(job 내 센터별 세션 재사용), `fetch`=프로젝트 폴더 탐색→재귀 순회→
  `AGENT_DOWNLOAD_BASE_DIR/<NFC 프로젝트번호>/<NFC 상대경로>/` 에 다운로드(NFC + 무결성 검증).
  Playwright/pywinauto/에이전트 락 **불필요**. HTTP 클라이언트는 `ecm_http_client.DestinyECM`.
  설계·결정: `12_http_ecm_source_decisions.md`.
- `LocalFolderArtifactSource`(`local`): `source_root/<프로젝트번호>` → 다운로드 폴더로 복사.
  다른 저장소 연결 첫 구현이자 fake-live 더블.
- `build_artifact_source(name, *, headless, source_root)`: 이름으로 구현체 생성
  (`ecm-http` / `local`). 레거시 Playwright source(`ecm`)는 제거됨 — `ecm` 값은 `ecm-http` 로 별칭 처리.

## 4. 워커가 쓰는 방식

`_run_live_job` (ecm_download_review_worker.py)

```python
source = build_artifact_source(
    source_name or settings.DOWNLOAD_REVIEW_SOURCE,   # 기본 "ecm-http"
    headless=headless,
    source_root=settings.LOCAL_ARTIFACT_SOURCE_ROOT,
)
await source.open()
try:
    for project in projects:
        ...
        await _clear_project_download_dir(job, project)   # 다운로드 폴더 사전 정리(모든 source 공통)
        ecm_result = await source.fetch(project, on_progress=..., is_canceled=...)
        # 이후: verify → archive → inspection → 상태/정리 (source-agnostic)
finally:
    await source.close()
```

### 책임 경계 주의

- **ECM 에이전트 락**: HTTP 직접연동(`ecm-http`)은 락이 불필요하다(팝업/단일 Windows 에이전트 없음).
  (에이전트 락은 이제 이력 조회의 레거시 Playwright URL 조회 경로에서만 쓰인다.)
- **다운로드 폴더 사전 정리(`_clear_project_download_dir`)**: 워커가 **모든 source 공통**으로 수행
  (같은 폴더로 다시 받을 때 덮어쓰기 팝업/혼입 방지). source-agnostic 한 "로컬 타깃 준비" 단계.

## 5. 새 저장소(source) 추가 방법

1. `artifact_source.py` 에 클래스 추가 — `open/close/fetch` 구현. `fetch` 는 산출물을
   `AGENT_DOWNLOAD_BASE_DIR/<프로젝트번호>` 에 만들고 `FetchResult` 반환.
   - 진행은 `await on_progress([상대경로], 건수)`, 취소는 `if await is_canceled(): raise JobCanceledError()`.
   - 동시성 제어가 필요하면 그 정책은 **이 클래스 안에서** (워커에 넣지 말 것).
2. `build_artifact_source()` 팩토리에 분기 추가.
3. 계약 테스트 추가(`ArtifactSourceSeamTests` 패턴) — ECM 없이 복사/누락/취소 검증.
4. 필요한 설정 키를 settings 에 추가하고 본 문서 §6 표 갱신.

워커·검증·점검 로직은 **건드릴 필요 없다**(계약만 지키면 됨).

## 6. 설정 / 실행 (fake-live 포함)

| 설정 | 기본 | 의미 |
|---|---|---|
| `DOWNLOAD_REVIEW_SOURCE` | `ecm-http` | source 기본값. `ecm-http` / `local` (레거시 `ecm` 은 `ecm-http` 로 별칭) |
| `LOCAL_ARTIFACT_SOURCE_ROOT` | `""` | local source 가 복사해 올 루트(`<root>/<프로젝트번호>`) |
| `ECM_USERNAME` / `ECM_PASSWORD` | `""` | ecm-http 상암·영남 공유 계정(환경변수 전용) |
| `ECM_USERNAME_BUNDANG` / `ECM_PASSWORD_BUNDANG` | `""` | ecm-http 분당 계정 |
| `ECM_ROOT_OID_{SANGAM,YEONGNAM,BUNDANG}` | 센터 기본값 | ecm-http 트리 탐색 시작 OID 덮어쓰기 |
| CLI `--source` | (없음) | 이 실행만 source 덮어쓰기. settings 보다 우선 |

- 운영(ECM, Playwright): `python manage.py run_download_worker --live`
- **HTTP 직접연동(ECM, requests)**: `python manage.py run_download_worker --live --source=ecm-http`
  (자격증명 환경변수 필요. 실서버 사전 검증: `python manage.py verify_ecm_http --center <센터> --test-no <시험번호> [--download]`)
- **fake-live(ECM 없이 전체 흐름)**:
  `LOCAL_ARTIFACT_SOURCE_ROOT=<폴더> python manage.py run_download_worker --once --live --source=local`
  → `<폴더>/<프로젝트번호>` 를 다운로드 폴더로 복사한 뒤, 이후 검증·점검 파이프라인을 그대로 실행.
- dry-run(상태 전이만, 다운로드 없음): `--dry-run` (기본; `--live` 없으면 dry-run).

## 7. 테스트

- `ArtifactSourceSeamTests`: 로컬 source 복사/누락/취소/팩토리(ECM 불요).
- `WorkerSourceSelectionTests`: `--source` 가 워커까지 전달되는지.
- `WorkerDownloadDirCleanupTests`: 사전 정리(팝업 잔여물) 동작.

## 8. 남은 작업

- source 별 동시성 선언(현재 락은 ECM 에 하드코딩). 필요 시 `ArtifactSource` 에 capability 노출.
- 실제 대체 저장소 구현 시 본 문서 §5 절차로 진행.
- 추적: `docs/INSPECTION_RULES_IMPROVEMENTS.md` §10.
