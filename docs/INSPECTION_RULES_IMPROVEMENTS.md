# 점검 규칙 관리 개선 로드맵

4인 전문가 페르소나 토론(2026-06-29)에서 합의된 개선안과 진행 상태를 추적한다.
새 세션에서도 맥락 없이 이어받을 수 있도록 각 항목에 "왜 / 무엇을 / 어디를" 기록한다.

## 진행 상태 요약

| # | 항목 | 상태 | 비고 |
|---|---|---|---|
| 1 | config_json 저장/시드 시점 검증 | ✅ **완료** (2026-06-29) | `main/rule_config_validation.py` |
| 2 | 정답/오류 샘플 골든 회귀 테스트 (CI) | ⬜ 미착수 | |
| 3 | `requires`/`produces` 기반 실행순서 자동화 | ⏸ **보류 (문서화됨)** | 본 문서 §3 |
| 4 | 규칙별 `engine_min_version` + 미지원 명시 경고 | ⬜ 미착수 | 로컬 앱 조용한 skip 방지 |
| 5 | 시드를 코드 → 선언 파일(YAML)로 분리 | ⬜ 미착수 | |
| 6 | 검사관용 규칙 편집 UI (폼+미리보기+롤백) | ⬜ 미착수 | |
| 7 | 테스트 라우팅 정렬 (ui_mock ↔ 운영) | ⏸ **보류 (재검토 조건 기록)** | 본 문서 §7 |

---

## 1. config_json 검증 — ✅ 완료

저장/시드 시점에 `rule_type` + `config_json`이 엔진 실행 가능한 형태인지 검사한다.

- 신규 모듈: `main/rule_config_validation.py` — `validate_rule_config()` / `validate_rule_spec()`
- 연결: `DownloadReviewRule.clean()`(Admin 경로) + `seed_download_review_rules._validate_specs()`(시드 게이트, DB 쓰기 전 전체 중단)
- 테스트: `main/tests.py::RuleConfigValidationTests` (11건)
- 검사 범위: 알 수 없는 rule_type / config 비객체 / 필수 키 / 리스트·정수 형식 / 확장자 `.` / 정규식 컴파일 / content_check 6종 / `required_files`·`folder_checks`·term-list 구조

---

## 3. requires/produces 기반 실행순서 자동화 — ⏸ 보류

### 왜 필요한가 (해결할 문제)

규칙 간 실행 순서가 **매직 넘버 `sort_order`** 로 암묵 인코딩돼 있다.
선행 규칙이 `raw_detail.variables`로 남긴 산출 변수를 후속 규칙이 소비하는데,
순서가 어긋나면 후속 규칙이 **빈 변수**를 받아 "부적합"을 낸다.

핵심 위험: 이 실패가 **제출물 결함처럼 위장**된다(실제로는 규칙 순서 문제).
그리고 Admin에 `list_editable = ("enabled", "sort_order")`가 있어 운영자가
목록 화면에서 순서를 직접 바꾸거나 규칙을 비활성화할 수 있다 → 실재하는 위험.

#1(config 형식 검증)은 이 오류를 잡지 못한다(config 형식은 멀쩡하므로).

### 산출 변수 의존 그래프 (구현의 기준)

`derived_variables` 흐름. `sort_order`가 이 순서와 모순되면 안 된다.

| 규칙 (rule_type) | requires (소비) | produces (생성) | 현재 sort_order |
|---|---|---|---|
| 시험성적서 (`test_report_document_check`) | — | `결함차수`, `1차`, `2차`, `시험성적서_세부사양표` | 95 |
| 시험계획서 (`test_plan_document_check`) | `시험성적서_세부사양표` | — | 96 |
| 결함리포트 (`defect_report_check`) | `결함차수` | `잔여결함수`, `H`, `R` | 100 |
| 테스트케이스 (`test_case_check`) | `잔여결함수` | — | 105 |
| 점검표 (`inspection_checklist_check`) | `H`, `R` | `측정항목별점수표` | 110 |
| 품질검사표 (`quality_inspection_table_check`) | `측정항목별점수표` | `품질부특성측정값` | 145 |
| 품질평가보고서 (`quality_evaluation_report_check`) | `품질부특성측정값` | — | 150 |

> ⚠️ `wd`, `start_date`, `project_number` 등은 `RuleContext`(프로젝트 메타데이터)에서
> 항상 제공되므로 의존 그래프에 포함하지 않는다. 그래프 대상은 **규칙이 만들어내는
> `derived_variables`** 뿐이다.

### 권장 진행 방식 — 2단계

#### 1단계 (가벼움, 먼저 권장): 선언 + 검증만

엔진 실행 로직은 그대로 두고, 메타데이터 선언과 저장 시점 검증만 추가한다.
#1과 동일한 "저장 시점 차단" 패턴이라 일관되고 엔진을 안 건드려 위험이 작다.

1. 각 규칙 `config_json`에 선택적 키 `requires: [str]`, `produces: [str]` 추가
   (시드 spec과 DB 양쪽). 위 표대로 채운다.
2. `main/rule_config_validation.py`에 **그래프 검증** 추가:
   - 입력: 활성 규칙 목록(+ `sort_order`, `requires`, `produces`).
   - 검사 A: 모든 `requires` 변수에 대해, **더 작은 `sort_order`** 를 가진 활성 규칙
     중 그 변수를 `produces` 하는 규칙이 존재하는가? 없으면 오류.
   - 검사 B: 순환 의존(위상정렬 불가) 없는가?
   - 메시지 예: `테스트케이스가 '잔여결함수'를 요구하지만 이를 생성하는 선행 활성 규칙이 없습니다(결함리포트 비활성/순서 역전 의심).`
3. 시드 `_validate_specs`와 `DownloadReviewRule.clean()`(또는 전체 규칙셋 검증 명령)에서 호출.
   - 단, `clean()`은 단일 규칙만 본다 → 그래프 검증은 **규칙셋 전체**가 필요하므로
     별도 진입점(예: `manage.py check_rule_graph` 또는 시드 게이트)에서 수행 권장.

#### 2단계 (전면): 위상정렬로 순서 자동 도출

`sort_order`를 순서의 원천에서 제거하고 `requires`/`produces`로 위상정렬한다.

1. `gscert_review_core/engine.py::evaluate_rules`(약 line 5059)에서 규칙 실행 순서를
   `sort_order` 정렬 대신 **위상정렬 결과**로 대체.
2. `sort_order`는 "동순위 표시 순서" 정도로 의미 축소(또는 tie-breaker).
3. 위상정렬 불가/누락 시 명확한 오류로 중단(점검 시작 전).

### 관련 코드 위치

- 변수 생성/소비: `gscert_review_core/engine.py` 각 `_evaluate_*` 핸들러의
  `raw_detail["variables"]` 및 `context.derived_variables`.
- 변수 수집: `main/views/review/ecm_download_review_inspection.py::get_rule_output_variables`,
  `_raw_detail_variables`.
- 현재 순서 결정: `inspection_rule` 정렬 `("sort_order", "name", "id")`
  (`run_download_inspection`, `_serialized_enabled_rules`, 모델 `Meta.ordering`).
- 매직 넘버 출처: `seed_download_review_rules.py::_rule_sort_order` (95/96/105/145 조정).

### 검증 방법

- `TTA-26-00018(정답)` → 전 규칙 pass, `TTA-26-00018(오류)` → 의도된 규칙만 fail.
- 추가: 결함리포트를 비활성화한 규칙셋 → 그래프 검증이 **오류로 차단**하는지 확인.
- 추가: 테스트케이스 sort_order를 결함리포트보다 앞으로 옮긴 규칙셋 → 검사 A가 잡는지 확인.

### 보류 사유

동작 자체는 현재 매직 넘버로 정상이며, 변경 비용(엔진 수정 + 변수 매핑 추출)이
#1보다 크다. 위험 vector(Admin 편집)는 실재하므로 우선순위는 중간.
재개 시 **1단계(검증만)** 부터 진행 권장.

---

## 7. 테스트 DB 라우팅 정렬 (ui_mock ↔ 운영) — ⏸ 보류

### 배경 (2026-06-29 조사 결과)

테스트는 `manage.py test main.tests --settings=myproject.ui_mock_settings`로 돌린다.
그런데 규칙 DB 라우팅이 운영과 다르다:

| | 운영 `settings.py` | `ui_mock_settings.py` |
|---|---|---|
| `downloadreviewrule` 위치 | `reference` (PostgreSQL) | `workflow` (SQLite, `WORKFLOW_MODEL_NAMES`) |
| `reference` alias | 있음 | **없음** |
| Reference 라우터 | 활성 | 미등록 |

이전에 전체 테스트가 `table "inspection_rule" already exists`로 깨졌는데,
이는 마이그레이션 0006이 fresh DB에서 0001과 같은 alias에 테이블을 재생성했기 때문이다.
→ **0006을 멱등(RunPython + 존재 확인)으로 고쳐 해결**했고, 66개 전부 통과한다.
(라우팅 차이 자체는 그대로 남겨둔 상태.)

### 보류 결정 + 재검토 조건 ⚠️

현재 **교차 DB(cross-DB) 쿼리 위험이 낮아** 라우팅 정렬은 보류한다. 근거:
- `DownloadReviewRule`(reference)을 가리키는 FK/M2M 없음(0005에서 제거, `rule_code`/`rule_name`
  스칼라로 비정규화 — `main/models.py` 주석 참조).
- 모든 rule 쿼리는 `DownloadReviewRule.objects` 단독. 유일한 prefetch(`rule_results`)는
  Project→RuleResult로 둘 다 workflow(동일 DB).
- inspection_rule을 workflow 테이블과 조인하는 raw SQL/`.using()` 혼용 없음.

따라서 ui_mock(rule→workflow 단일 DB)이 운영(2-DB)을 못 흉내내도 잡을 버그가 없다.

**다음 중 하나라도 발생하면 즉시 재검토** (그 순간 ui_mock 테스트가 운영 버그를 못 잡게 됨):
- `DownloadReviewRule`에 FK를 다시 추가(예: `RuleResult.rule` 복원)하거나
  rule ↔ workflow 모델을 한 쿼리로 관계 traversal(`rule__...`, `select_related`/`prefetch`)
- rule과 workflow 테이블을 조인하는 raw SQL 추가
- PostgreSQL 고유 동작(JSONField 쿼리/제약 등)에 의존하는 rule 로직 추가

### 재검토 시 선택지 (권장순)

1. **공통 base 설정 + 얇은 테스트 override**로 라우팅을 한 곳에서 정의 → 설정 모듈 2개가
   따로 노는 근본 드리프트를 제거(이번 사고의 뿌리). ui_mock 수기 패치보다 우선.
2. CI가 PostgreSQL 가능하면 → reference를 **실제 PG**로 쓰는 테스트 설정(완전 충실도).
3. 최소 절충: ui_mock에 `reference`(SQLite) alias + `ReferenceDatabaseRouter` 추가하고
   `downloadreviewrule`을 `WORKFLOW_MODEL_NAMES`에서 빼 `REFERENCE_MODEL_NAMES`로 이동.
   (구조 parity는 얻지만 PG 엔진 parity는 못 얻음.)

> 주의: 0006은 이미 멱등이므로 어느 선택지든 fresh DB 충돌은 재발하지 않는다.
