# GSCert 리팩터링 진행 기록

이 문서는 2026-06 진행한 세 갈래 작업의 단계별 내용과 상태를 정리한다.

1. reference 데이터 PostgreSQL 전환
2. 로컬 검토 프로그램(PySide6) 개선
3. **점검 엔진 공유 리팩터링 (웹 + 로컬 공용 `gscert_review_core`)** — 핵심 진행 항목

---

## 1. reference 데이터 PostgreSQL 전환 ✅

기존 `main/data/reference.db`(SQLite, `sw_data` 9,121행)를 PostgreSQL `gscert_reference` DB로 완전 이전했다.

**목적**: 웹 SQLite와 분리된 참조 DB를 로컬 앱에서 API로 활용하고, 이후 reference는 모두 PostgreSQL로 대체.

**접속 정보**: `localhost:5432` / DB `gscert_reference` / user `postgres` — 비밀번호는 `env.ps1`(gitignored)에 저장. `start_server.ps1`, `start_worker.ps1`, `launcher.ps1` 시작 시 자동 로드.

**구현 파일**
- `myproject/settings.py` — `reference` DB 알리아스(`REFERENCE_PG_*`), `ReferenceDatabaseRouter`
- `main/models.py` — `SwData` 모델 (`db_table='sw_data'`)
- `main/db_routers.py` — `ReferenceDatabaseRouter` (SwData → reference DB)
- `main/migrations/0003_swdata.py` — sw_data 테이블 생성
- `main/management/commands/import_reference_db.py` — SQLite/xlsx → PostgreSQL 적재 (`--source`, `--source-xlsx`, `--clear`)
- `main/views/reference_search.py` + `main/urls.py` — `GET /api/reference/search/`
- `local_review_app/.../api_client.py`, `app.py` — `ReferenceItem`, GS 검색 다이얼로그

### 1-2. weekly.py / 임베딩 PostgreSQL 전환 ✅
- `main/utils/weekly.py` — `sync_reference_db()`가 `manage.py sqlite reference.xlsx reference.db` 대신 `manage.py import_reference_db --source-xlsx reference.xlsx`로 PostgreSQL에 직접 적재(A안: SQLite 중간단계 제거)
- `main/utils/embedding_to_faiss.py` — `fetch_texts_from_pg()`, `build_faiss_from_pg()` 추가 (PostgreSQL SwData에서 직접 읽어 FAISS **증분** 갱신)
- `main/management/commands/embed_db.py` — `db_path` 생략 시 PostgreSQL 소스 사용
- `launcher.ps1` — `W`(weekly 동기화), `I`(FAISS 증분 임베딩) 메뉴 추가

### 1-3. 웹 reference.db 사용처 → PostgreSQL ✅
- `main/views/testing/history.py` — 시험 이력 조회를 `SwData.objects.using('reference')` ORM으로 전환
- `main/views/testing/similar_compare.py` — 유사 시험 조회의 DB 조회를 ORM으로 전환 (FAISS 인덱스는 그대로)
- `main/views/certy/prdinfo_db.py` — 제품정보 조회 ORM 전환
- `main/views/server_console.py` — 임베딩 실행을 현재 시스템(`C:\Claude_GSCert`, PostgreSQL)으로 수정

---

## 2. 로컬 검토 프로그램(PySide6) 개선 ✅

`local_review_app/gscert_local_review/app.py`, `scanner.py`

- **배경 흰색화**: 회색 배경(`#f4f6f8`) → 흰색(`#ffffff`)으로 가독성 개선
- **버튼 글자 깨짐 수정**: 한글이 잘리던 버튼들의 `setFixedWidth` → `setMinimumWidth`
- **폴더 스캔 응답없음 해결**: `scan_folder`에 진행 콜백 추가, `ScanWorker(QThread)`로 백그라운드 스캔. 스캔 중 인디케이터 프로그레스바 + "스캔 중… N개" 실시간 표시 + 버튼 비활성화

---

## 3. 점검 엔진 공유 리팩터링 (핵심)

### 배경 / 문제
로컬 검토 프로그램이 활성 규칙 18개 중 **9개를 "미지원"으로 처리**(절반). 원인은 웹이 서버 엔진 `main/views/review/ecm_download_review_inspection.py`(약 5,400줄)로 문서 내용까지 정밀 검사하는 반면, 로컬 `local_runner.py`(약 740줄)는 파일 존재 + 일부 Word/PDF만 재구현했기 때문.

미지원 9종: 기능리스트 / 시험계획서 / 테스트케이스 / 결함보고서 / 점검표 / 시험성적서 / 품질평가표 / 품질검사표 / 이미지 스크린샷 날짜.

### 배포 구조
검토자 PC가 서버에서 **규칙(rule bundle)만 다운로드** → 검토자 PC에서 로컬 파일을 직접 점검. 서버는 로컬 파일에 접근 불가.

### 방향 (확정)
**공유 엔진 리팩터링** — 저장소 루트에 Django 비종속 `gscert_review_core/` 패키지를 만들어 웹과 로컬이 동일 코드를 사용한다.

```
gscert_review_core/
  __init__.py
  types.py       # 상태상수, EngineFile, RuleSpec, RuleContext, RuleEvaluation
  documents.py   # Word/Excel/PDF 파서 (bytes 입력) — 서버 검증 코드 이식
  artifacts.py   # ArtifactSink 인터페이스 (웹=DB저장 / 로컬=no-op)
  engine.py      # 평가 로직 전체 이식, Django 의존 제거
```

핵심 설계
- **파일 I/O 분리**: 코어는 파일 경로/바이트 기반. 웹 어댑터=zip 내부/.doc 변환 처리, 로컬 어댑터=디스크 읽기.
- **산출물**: 웹은 PDF/Excel 캡처를 DB에 저장하지만 로컬은 PASS/FAIL만 필요 → `ArtifactSink`로 추상화(로컬 no-op).
- **RuleContext**: 로컬은 `ProjectMetadata`(API)로, 웹은 ecm_row_json + PostgreSQL에서 구성.

### 단계별 진행 상태

| 단계 | 내용 | 상태 |
|---|---|---|
| Phase 1 | 코어 토대: `types.py` / `documents.py` / `artifacts.py` | ✅ 완료 |
| Phase 2 | `engine.py`로 평가 로직 이식 + Django 의존 제거 | ✅ 완료 |
| Phase 3 | 웹 파일을 코어 위임 thin-adapter로 전환 + **회귀 검증** | ⏳ 예정 |
| Phase 4 | 로컬 `local_runner.py`를 코어 위임으로 전환 | ⏳ 예정 |
| Phase 5 | 로컬 앱 패키징에 코어 + deps(lxml/xlrd/fitz) 번들 | ⏳ 예정 |

#### Phase 1 (완료)
- `types.py`: 상태상수(`PASS/FAIL/UNSUPPORTED/ERROR`), `EngineFile`(reader 콜백·경로 세그먼트), `RuleSpec`(`config_json` 호환), `RuleContext`, `RuleEvaluation`
- `documents.py`: 서버 파서를 bytes 입력으로 이식 — `read_docx`(문단/표/머리글/바닥글 + 순서 보존 body), `read_excel`(.xlsx openpyxl + .xls BIFF 머리/바닥글), `read_pdf_text`
- `artifacts.py`: `ArtifactSink` 프로토콜 + 로컬용 `NoOpArtifactSink`
- 실제 의존성(lxml/openpyxl/fitz)으로 import·동작 검증 완료

#### Phase 2 (완료)
- 서버 엔진을 `engine.py`로 그대로 복사 후 변환 스크립트로 **Django 결합만 제거**
- Django 없이 import 검증 완료 (함수 209개, 평가기 22개, 잔존 Django 참조 0)
- 공개 진입점:
  - `engine.evaluate_rules(rules, context, files, project=None, sink=None)`
  - `engine.build_context(...)`
  - `engine.set_artifact_sink(sink)`
  - shim `engine.DownloadReviewRuleStatus`(`pass/fail/error/warning`), `engine.FileInfo`
- 코어에서 제거 → Phase 3에서 웹으로 이관할 함수: `run_download_inspection`, `cleanup_download_dir`, `get_rule_output_variables`, `_build_rule_context`, `_reference_start_end_dates`(+sqlite 헬퍼), `_artifact_results_from_evaluations`/`_artifact_column`, `_find_temp_files`, `_validate_cleanup_target`, 산출물 저장 내부(`_store_artifact_bytes`/`_artifact_base_dir`/`_render_excel_area_png`/폰트/`_excel_area_values`/`_artifact_cell_text`/`_safe_artifact_suffix`)
- 3개 `_store_*`는 sink 위임으로 대체

### Phase 3 위험 요소 (변경 전 반드시 방어)

**🔴 높음 — 조용히 잘못된 판정**
1. **`_reference_start_end_dates`의 SQLite reference.db 의존**: PostgreSQL 전환으로 reference.db가 stale/없으면 `start_date`/`end_date`가 빈 값이 되어 이미지 날짜·작성일·결함리포트 날짜 등 여러 평가기가 예외 없이 FAIL. → SwData(PostgreSQL) 조회로 전환 필요.
2. **전역 `_ARTIFACT_SINK` + 동시 점검**: 멀티스레드에서 두 프로젝트 동시 점검 시 sink가 덮어써져 산출물이 엉뚱한 project에 저장될 수 있음. → contextvar/스레드로컬 또는 직렬화.
3. **`_soffice_executable`의 settings 폴백 제거**: `.doc` 변환 경로 설정이 사라짐. → 웹 시작 시 `os.environ["AGENT_SOFFICE_PATH"]`로 보존.

**🟡 중간 — 즉시 드러나는 깨짐**
4. **FileInfo 호환성**: 웹 `ecm_download_verify.FileInfo`와 코어 `engine.FileInfo`가 한 리스트에 혼재. `.name/.path/.size/.extension/.modified_at` 의미·`::` 경로 규약 일치 필요.
5. **`verify_result`에 캐시 속성 setattr**: 코어가 `_inspection_files_cache` 등을 setattr. frozen/`__slots__`면 예외.
6. **산출물 dict/경로 규칙 불일치**: `WebArtifactSink` 반환 dict가 기존과 완전히 동일해야 UI 안 깨짐.
7. **RuleEvaluation 클래스 혼선**: 웹 매핑은 `evaluation.rule.code`/`.sequence`를 읽으므로 반드시 `engine.RuleEvaluation` 사용.

**🟢 낮음 — 점검 항목**
8. 상태 문자열 정합성(shim 값 = 모델 `.value`)
9. `raw_detail_json` 직렬화 타입
10. import 경로/배포(repo 루트 `sys.path`, 코어가 배포 산출물에 포함)

**Phase 3 통과 기준**: 동일 프로젝트 before/after `DownloadReviewRuleResult`(status/expected/actual/message/raw_detail) **0 diff**. → 검증용 실제 다운로드 프로젝트 1건 필요.
