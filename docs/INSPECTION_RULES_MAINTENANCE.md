# 점검 규칙 수정 매뉴얼

점검 규칙을 **유동적으로 변경**하기 위해 현재 시스템은 "코드 시드 → DB 저장 → JSON 번들 배포 → 엔진 실행" 구조를 씁니다.
이 문서는 운영 중 규칙을 안전하게 바꾸는 방법을 단계별로 설명합니다.

---

## 1. 전체 구조 한눈에 보기

```
seed_download_review_rules.py   ① 규칙 정의(코드, config_json)
        │  python manage.py seed_download_review_rules ...
        ▼
inspection_rule  (DB 테이블, 모델 DownloadReviewRule)   ② 단일 진실 원본(SoT)
        │  ecm_rulebase.py 가 enabled=True 규칙을 직렬화
        ▼
rulebase 번들 JSON  (API: manifest/bundle)              ③ 배포 포맷
        │  로컬앱이 rules_bundle.json 으로 캐시 (rule_cache.py)
        ▼
gscert_review_core/engine.py    ④ rule_type 별 핸들러가 실행
        ▼
inspection_result  (DB)  → ecm_download_review.js  ⑤ 기대값/실제값 표시
```

- **DB가 단일 진실 원본**입니다. 운영 점검은 항상 `inspection_rule` 테이블(주 서버 PostgreSQL `reference`)을 읽습니다.
- 시드 파일은 "초기/기준 규칙을 코드로 박아두고 재현"하는 용도입니다.
- JSON 번들은 로컬 점검 앱이 서버 없이 동작하도록 **DB → JSON으로 export한 사본**입니다(직접 편집 대상 아님).

### 규칙 1건의 구성 (`DownloadReviewRule` 필드)

| 필드 | 설명 |
|---|---|
| `code` | 고유 코드(예: `artifact_01`). 시드/매칭 키 |
| `name` | 표시 이름(= 산출물 컬럼명) |
| `rule_type` | 실행 핸들러 종류(엔진이 분기) |
| `config_json` | **규칙의 모든 파라미터**(폴더/파일명/검사 항목/메시지) |
| `target_file_type` | `pdf`/`xlsx`/`any` 등 |
| `severity` | `error`/`warning`/`info` |
| `enabled` | 활성 여부(점검 시 `True`만 실행) |
| `sort_order` | 실행 순서(**산출 변수 의존성에 영향**) |
| `version` | 규칙 버전 태그(`actual-1` 등) |

---

## 2. 어떤 변경이 어디서 이뤄지나 (난이도별)

| 변경 유형 | 방법 | 코드 수정 필요? |
|---|---|---|
| 기대 문구·메시지·키워드·확장자·개수 변경 | `config_json` 값만 수정 | ❌ (DB만) |
| 폴더 키워드 체인 변경 | `config_json.folder_keyword_chain` | ❌ |
| 규칙 일시 비활성화 | `enabled=False` | ❌ |
| 실행 순서 변경 | `sort_order` | ❌ (단, 변수 의존 주의) |
| 기존 검사에 항목 추가(같은 type 내) | `config_json.content_checks` 등 배열에 항목 추가 | ❌ (지원되는 sub-type이면) |
| **완전히 새로운 검사 로직** | `engine.py`에 새 `rule_type` 핸들러 추가 | ✅ |

➡️ **대부분의 운영 변경은 `config_json` 수정만으로 가능**합니다. 코드 배포 없이 DB만 바꾸면 됩니다.

---

## 3. 규칙 수정 절차

### 방법 A. config_json 값만 바꾸기 (가장 흔함, 코드 불필요)

1. **시드 파일을 기준값으로 함께 갱신**(재현성 유지). `seed_download_review_rules.py`의 해당 `column_name` 블록에서 값을 수정.
   - 예: 검토자 이름을 바꾸려면 테스트케이스 블록의 `"reviewer_expected": "김진영"` 수정.
2. DB에 반영:
   ```bash
   python manage.py seed_download_review_rules --only-real --update-existing --dry-run   # 미리보기
   python manage.py seed_download_review_rules --only-real --update-existing             # 실제 반영
   ```
   - `--update-existing`가 있어야 기존 규칙의 `config_json`/`name`/`sort_order` 등이 갱신됩니다.
   - `--dry-run`으로 created/updated/unchanged 건수를 먼저 확인하세요.
   - ⚙️ **자동 검증**: 시드는 DB에 쓰기 전 모든 규칙의 `config_json`을 검증합니다. 잘못된 값이 하나라도 있으면 `CommandError`로 **전체 중단**되고(부분 반영 없음) 오류 목록이 출력됩니다. `--dry-run`에서도 동일하게 검증합니다. → §3 끝 "자동 검증" 참조.
3. (선택) Django Admin이나 DB에서 직접 `config_json`만 빠르게 바꿔도 됩니다. 단, 시드 파일과 어긋나면 다음 시드 실행 때 덮어써질 수 있으니 **시드 파일도 함께 맞추세요.**
   - ⚙️ Admin에서 저장하면 `DownloadReviewRule.clean()`이 같은 검증을 수행하므로, 잘못된 `config_json`은 저장 단계에서 막힙니다(`config_json` 필드에 오류 표시).
4. 로컬 점검 앱은 다음 실행 시 rulebase 번들을 다시 받아 `rules_bundle.json`을 갱신합니다(체크섬/버전 변경 자동 감지).

### 방법 B. 규칙 켜고/끄기

```bash
python manage.py seed_download_review_rules --only-real --enable    # 전체 활성화
python manage.py seed_download_review_rules --only-real --disable   # 전체 비활성화
```
개별 규칙만 끄려면 DB에서 해당 행 `enabled=False`로 변경(점검 시 자동 제외).

### 방법 C. 새로운 검사 항목 추가 (지원되는 sub-type)

`document_artifact_check`의 `content_checks` 배열에 항목 추가가 가장 쉽습니다. 지원 sub-type:

| sub-type | 용도 | 필수 키 |
|---|---|---|
| `docx_text_contains` | 본문에 문구 포함 | `text` 또는 `texts` |
| `docx_header_contains` / `docx_footer_contains` | 머리글/바닥글 포함 | `text` |
| `docx_table_next_cell_equals` | 표 라벨 우측 셀 일치 | `label`, `expected` |
| `docx_next_paragraph_matches` | 특정 문단 다음 줄 정규식 | `after_text(s)`, `regex` |
| `pdf_first_page_label_value_contains` | PDF 1페이지 라벨 주변 포함 | `label`, `expected` |

예시(합의서에 새 머리글 검사 추가):
```json
{
  "type": "docx_header_contains",
  "extensions": [".docx", ".docm"],
  "text": "{company}",
  "failure_message": "머리글에 회사명이 없습니다."
}
```

> ⚙️ 위 sub-type 목록과 필수 키는 자동 검증으로 **강제**됩니다. 목록에 없는 `type`을 쓰거나
> 필수 키(`label`/`expected`/`regex` 등)를 빠뜨리면 저장/시드 단계에서 차단됩니다.
> (이전에는 점검 *실행 중*에야 오류가 나서 점검이 중단됐습니다.)

### 방법 D. 완전히 새로운 rule_type 추가 (코드 필요)

1. `gscert_review_core/engine.py`에 `_evaluate_<새타입>()` 핸들러 작성 → `RuleEvaluation` 반환
   (반드시 `expected`, `actual`, `status`, `message`, 가능하면 `raw_detail.sub_checks` 채울 것).
2. 엔진의 `rule_type → 핸들러` 디스패치 테이블에 등록. **`gscert_review_core/engine.py`의 `SUPPORTED_RULE_TYPES`에도 새 type을 추가**해야 합니다. 자동 검증이 이 집합에 없는 `rule_type`을 거부하므로, 빠뜨리면 시드/저장이 막힙니다(엔진 디스패치와 검증의 단일 진실 소스).
3. (필요 시) 새 type 전용 필수 키/구조를 `main/rule_config_validation.py`에 추가하면 그 type도 형식 검증을 받습니다.
4. `seed_download_review_rules.py`에 해당 컬럼 spec 추가(`rule_type` + `config_json`).
5. `engine.py` 변경 시 `RULE_ENGINE_MIN_VERSION`(ecm_rulebase.py) 호환성 확인 — 로컬 앱 엔진이 구버전이면 새 type을 모를 수 있음.
6. 시드 재실행 + 로컬 앱 엔진 업데이트.

### 자동 검증 (config_json) — 모든 변경에 공통 적용

규칙을 저장하기 전에 `config_json`이 엔진 실행 가능한 형태인지 자동 검사합니다.
**목적**: 잘못된 config(오타·타입 오류·알 수 없는 검사 유형)가 점검 *실행 중*에
점검 전체를 멈추는 사고를 막고, 그 오류를 *저장 시점*으로 앞당기는 것.

- **검증 모듈**: `main/rule_config_validation.py` (`validate_rule_config` / `validate_rule_spec`)
- **동작 지점**
  - 시드: `manage.py seed_download_review_rules` 실행 시(`--dry-run` 포함) → 오류 있으면 전체 중단
  - Admin: 규칙 저장 시 `DownloadReviewRule.clean()` → `config_json` 필드 오류로 차단
- **검사 항목**
  - `rule_type`이 엔진 `SUPPORTED_RULE_TYPES`에 있는가
  - `config_json`이 객체인가 / rule_type별 필수 키가 있는가
  - 리스트·정수 형식, 확장자가 `.`으로 시작하는가
  - 정규식(`version_pattern`, content_check `regex`)이 컴파일되는가
  - `content_checks` 항목의 `type`이 지원 목록에 있고 필수 키를 갖췄는가
  - `required_files` / `folder_checks` / 금지·필수어 목록 구조
- **경고(저장은 허용)**: `artifact_column` 누락 시 "기준 DB 컬럼 매핑 안 될 수 있음" 경고 출력
- **검증 자체 테스트**: `main/tests.py::RuleConfigValidationTests`
- **검증기 확장**: 새 키/구조 규칙을 추가하려면 `main/rule_config_validation.py`의
  `_RULE_REQUIRED_KEYS`, `_LIST_OF_STR_KEYS`, `_INT_KEYS`, `_CONTENT_CHECKS` 등을 수정.

> 검증을 통과해도 "값이 의미상 맞는지"(예: 검토자 이름이 실제로 맞는지)는 보장하지 않습니다.
> 그건 §5-6의 정답/오류 샘플 회귀 점검으로 확인하세요.

---

## 4. config_json 작성 시 치환 플레이스홀더

값 안에서 아래 토큰을 쓰면 점검 시점에 프로젝트 데이터로 치환됩니다.

| 토큰 | 치환 값 |
|---|---|
| `{project_number}` / `{프로젝트번호}` | 프로젝트 번호 |
| `{product}` / `{제품명}` | 제품명 |
| `{company}` / `{회사명}` | 회사명 |
| `{pl}` / `{PL}` | 시험 PL |
| `{wd}` / `{WD}` | WD |
| `{시작일}` `{종료일}` | 시험 시작/종료일 |
| `{연도}` | 연도 |
| `{신청일}` `{계약일}` `{인증위}` | 신청/계약/인증위 날짜 |
| `{임의KEY}` | 선행 규칙이 `raw_detail.variables`로 남긴 산출 변수 |

---

## 5. 주의사항 (실수하기 쉬운 부분)

1. **`sort_order`와 산출 변수 의존성**
   - 시험성적서(95)→결함리포트(100)→테스트케이스(105)→점검표(110)→품질검사표(145)→품질평가보고서(150) 순으로
     앞 규칙이 만든 변수(`결함차수`, `잔여결함수`, `H`, `R`, `측정항목별점수표`, `품질부특성측정값` 등)를 뒤 규칙이 사용.
   - 순서를 바꾸면 후속 규칙이 빈 변수를 받아 부적합/오류가 날 수 있습니다. (`docs/INSPECTION_RULES_TABLE.md` §8 참조)

2. **`code`는 절대 바꾸지 말 것** — 시드 매칭 키이자 결과 추적 키(`inspection_result.rule_code`)입니다.

3. **JSON 번들은 직접 편집 금지** — DB에서 export되는 사본입니다. 편집해도 다음 동기화 때 덮어써집니다.

4. **공백·서식 민감 항목** — 서명란(`성  명 : 김  성  희`)처럼 공백 형식까지 비교하는 값이 있습니다. 복사 시 공백 그대로 유지. (이런 *값의 의미* 오류는 자동 검증이 잡지 못하므로 샘플 회귀 점검 필수.)

5. **사용자 안내문(`INSPECTION_RULES.md`)도 함께 갱신** — 규칙 의미가 바뀌면 제출자용 문서도 업데이트.

6. **반영 후 검증** — `TTA-26-00018(정답)`(통과)·`TTA-26-00018(오류)`(부적합) 샘플로 회귀 점검을 돌려 기대대로 동작하는지 확인.

---

## 6. 빠른 체크리스트

- [ ] 시드 파일(`seed_download_review_rules.py`) 해당 블록 수정
- [ ] `--dry-run`으로 변경 건수 확인 (**자동 검증 통과** 확인 — 오류·경고 메시지 점검)
- [ ] `--update-existing`로 DB 반영
- [ ] (코드 변경 시) 엔진 핸들러/디스패치/`SUPPORTED_RULE_TYPES`/`RULE_ENGINE_MIN_VERSION` 점검
- [ ] (새 type·구조 추가 시) `main/rule_config_validation.py` 검증 규칙 보강
- [ ] 정답/오류 샘플로 회귀 점검
- [ ] 사용자용 `INSPECTION_RULES.md` 동기화
- [ ] 로컬 앱이 새 rulebase 번들을 받는지 확인(버전/체크섬 변경)
