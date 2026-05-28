# 점검규칙 JSON 매뉴얼

## 목적

download-review의 각 산출물 점검 규칙은 `workflow.db`의 `inspection_rule` 테이블에 저장된다. 규칙별 세부 조건은 `config_json`에 JSON으로 들어간다.

이 구조의 목표는 명확하다. 문서에서 찾아가는 방식은 같고 값만 달라지는 경우, Python 코드를 계속 수정하지 않고 JSON만 바꿔 빠르게 조정할 수 있게 하는 것이다.

## 관련 문서와 코드

| 항목 | 위치 |
| --- | --- |
| 이 매뉴얼 | `main/docs/19_inspection_rule_manual.md` |
| 산출물 점검 설계 원문 | `main/docs/05_zip_inspection.md` |
| DB 구조 | `main/docs/02_database_design.md` |
| 규칙 seed 명령 | `main/management/commands/seed_download_review_rules.py` |
| 검사 엔진 | `main/views/review/ecm_download_review_inspection.py` |
| 결과 write-back | `main/views/review/ecm_reference_db.py` |
| Codex skill 요약 | `main/docs/codex_skills/gscert-download-review-maintainer/references/rules.md` |

## 전체 흐름

1. worker가 프로젝트 산출물을 다운로드하고 zip 또는 폴더를 확인한다.
2. `inspection_rule`에서 `enabled=True`인 규칙을 `sort_order` 순서로 읽는다.
3. 각 규칙의 `rule_type`에 맞는 Python 검사 함수가 실행된다.
4. 검사 함수는 `config_json`의 폴더, 파일명, 확장자, 개수, 문서 내용 조건을 사용한다.
5. 결과는 `inspection_result`에 저장된다.
6. `config_json.artifact_column`이 `ecm_list` 산출물 컬럼과 매핑되면 해당 컬럼에 `O` 또는 `X`가 write-back 된다.

## DB 필드

`inspection_rule`의 주요 필드는 다음과 같다.

| 필드 | 설명 |
| --- | --- |
| `code` | 규칙 코드. 현재 산출물 규칙은 `artifact_01`, `artifact_02` 형식 |
| `name` | UI와 결과에 보이는 규칙명 |
| `target_file_pattern` | 예전/단순 규칙용 파일명 패턴. 현재 실제 1~5번은 주로 JSON을 사용 |
| `target_file_type` | 기본 확장자 힌트. `pdf`, `docx`, `xlsx`, `any` 등 |
| `rule_type` | 어떤 검사 함수를 쓸지 결정하는 값 |
| `config_json` | 실제 규칙 조건 JSON |
| `severity` | 오류 수준. 현재는 주로 `error` |
| `enabled` | 규칙 활성 여부 |
| `version` | seed 버전. 실제 규칙은 현재 `actual-1` |
| `sort_order` | 실행 순서 |

결과는 `inspection_result`에 저장된다.

| 필드 | 설명 |
| --- | --- |
| `rule_code`, `rule_name` | 실행 당시 규칙 식별 정보 |
| `status` | `pass`, `fail`, `warning`, `error` |
| `expected` | 기대 조건 요약 |
| `actual` | 실제 매칭 결과 요약 |
| `message` | 사용자에게 보일 메시지 |
| `file_path`, `file_name` | 대표 파일 경로와 파일명 |
| `raw_detail_json` | 내부 확인용 상세 증거. 매칭 파일, 선택 폴더, content check 상세 포함 |

## 현재 실제 구현된 규칙

| 번호 | code | 산출물 컬럼 | rule_type | 핵심 조건 |
| --- | --- | --- | --- | --- |
| 1 | `artifact_01` | 계약서 | `required_artifact_file` | 계약 폴더, 계약서+프로젝트번호, `.pdf`, 1개 |
| 2 | `artifact_02` | 합의서(PDF) | `document_artifact_check` | 계약 폴더, 합의서+프로젝트번호, `.docx` 1개와 `.pdf` 1개, 시험신청번호 일치 |
| 3 | `artifact_03` | 수수료산정표 | `required_artifact_file` | 계약 폴더, 수수료산정표+프로젝트번호, `.xlsx`, 1개 |
| 4 | `artifact_04` | 시험환경구성도 | `required_artifact_file` | 시험/계획 폴더, 구성도+프로젝트번호, 확장자 무관, 1개 |
| 5 | `artifact_05` | 품질특성별제품정보기재사항 | `document_artifact_check` | 시험/계획 폴더, 품질특성별+프로젝트번호, `.docx`, 제목/날짜 검사 |

## 공통 JSON 키

| 키 | 사용 위치 | 설명 |
| --- | --- | --- |
| `artifact_column` | 모든 실제 산출물 규칙 | write-back할 `ecm_list` 산출물 컬럼명 |
| `folder_keyword_chain` | 파일 탐색 | 폴더 경로에서 순서대로 찾아야 하는 키워드 목록 |
| `filename_keywords` | 파일명 탐색 | 파일명에 모두 들어가야 하는 키워드 목록 |
| `extensions` | 파일 탐색 | 허용 확장자. 비우면 확장자 무관 |
| `exact_count` | 파일 개수 | 정확히 몇 개여야 하는지 |
| `min_count` | 파일 개수 | 최소 몇 개 이상이어야 하는지. `exact_count`가 있으면 우선 |
| `required_files` | 문서 검사 | 같은 파일명 조건으로 잡힌 파일 중 확장자별 필수 개수 |
| `content_checks` | 문서 검사 | docx/pdf 내부 내용 검사 목록 |
| `missing_message` | 실패 메시지 | 파일이 없거나 필수 조건이 빠졌을 때 |
| `multiple_message` | 실패 메시지 | `exact_count`보다 많이 잡혔을 때 |
| `pass_message` | 성공 메시지 | 규칙 통과 시 표시 |

## 변수 치환

JSON 문자열에는 프로젝트 기준정보를 넣을 수 있다.

| 플레이스홀더 | 값 |
| --- | --- |
| `{project_number}`, `{프로젝트번호}` | 프로젝트 번호 |
| `{product}`, `{제품명}` | 제품명 |
| `{pl}`, `{PL}` | 시험PL |
| `{wd}`, `{WD}` | Google Sheet F열에서 가져온 WD |

예를 들어 `filename_keywords`에 `["합의서", "{project_number}"]`를 넣으면 실제 검사 시 `["합의서", "TTA-26-00266"]`처럼 바뀐다.

## 폴더와 파일 매칭 방식

`folder_keyword_chain`은 폴더 경로에서 키워드를 순서대로 찾는다.

예를 들어 `["시험", "계획"]`이면 경로 중 먼저 `시험`이 들어간 폴더를 찾고, 그 뒤에서 `계획`이 들어간 폴더를 찾는다. 조건을 만족하는 첫 폴더가 선택되면 그 하위 파일만 검사한다.

`filename_keywords`는 파일명에 모든 키워드가 포함되는지 본다. 키워드 순서는 상관없다.

`extensions`는 확장자를 제한한다. `[]` 또는 생략된 확장자가 `any`인 경우 확장자 제한을 두지 않는다.

## rule_type: required_artifact_file

파일 존재, 폴더, 파일명, 확장자, 개수만 확인하는 규칙이다.

계약서 규칙 예시는 다음과 같다.

```json
{
  "artifact_column": "계약서",
  "folder_keyword_chain": ["계약"],
  "filename_keywords": ["계약서", "{project_number}"],
  "extensions": [".pdf"],
  "exact_count": 1,
  "missing_message": "파일이 없습니다.",
  "pass_message": "계약서 PDF 파일을 확인했습니다."
}
```

자주 바꾸는 값은 `folder_keyword_chain`, `filename_keywords`, `extensions`, `exact_count`, `missing_message`, `multiple_message`, `pass_message`다.

## rule_type: document_artifact_check

파일 존재 검사에 더해 docx/pdf 내부 내용을 확인하는 규칙이다.

합의서 규칙 예시는 다음과 같다.

```json
{
  "artifact_column": "합의서(PDF)",
  "folder_keyword_chain": ["계약"],
  "filename_keywords": ["합의서", "{project_number}"],
  "required_files": [
    {"extensions": [".docx"], "exact_count": 1},
    {"extensions": [".pdf"], "exact_count": 1}
  ],
  "content_checks": [
    {
      "type": "docx_table_next_cell_equals",
      "extensions": [".docx"],
      "label": "시험신청번호",
      "expected": "{project_number}",
      "failure_message": "프로젝트 번호가 맞지 않습니다."
    },
    {
      "type": "pdf_first_page_label_value_contains",
      "extensions": [".pdf"],
      "label": "시험신청번호",
      "expected": "{project_number}",
      "line_window": 3,
      "failure_message": "프로젝트 번호가 맞지 않습니다."
    }
  ],
  "missing_message": "필요한 합의서 파일이 없습니다.",
  "pass_message": "합의서 docx/pdf와 시험신청번호를 확인했습니다."
}
```

품질특성별제품정보기재사항처럼 특정 제목과 그 다음 문단의 날짜를 보는 규칙은 `docx_text_contains`와 `docx_next_paragraph_matches`를 함께 쓴다.

## 문서 내용 검사 타입

| type | 대상 | 주요 키 | 검사 방식 |
| --- | --- | --- | --- |
| `docx_table_next_cell_equals` | `.docx` | `label`, `expected` | Word 표에서 label 셀을 찾고 오른쪽 셀이 expected와 같은지 확인 |
| `pdf_first_page_label_value_contains` | `.pdf` | `label`, `expected`, `page_index`, `line_window` | PDF 지정 페이지에서 label 주변 줄에 expected가 포함되는지 확인 |
| `docx_text_contains` | `.docx` | `text` | Word 문단 중 text가 포함된 문단이 있는지 확인 |
| `docx_next_paragraph_matches` | `.docx` | `after_text`, `regex` | after_text 문단 다음의 첫 비어 있지 않은 문단이 regex와 맞는지 확인 |

공통 보정 옵션은 다음과 같다.

| 키 | 설명 |
| --- | --- |
| `remove_whitespace` | 모든 공백을 제거하고 비교 |
| `normalize_whitespace` | 여러 공백을 하나로 줄여 비교. 일부 비교는 기본값이 true |
| `failure_message` | 해당 content check 실패 시 메시지 |
| `missing_message` | 해당 확장자의 검사 대상 파일이 없을 때 메시지 |
| `pass_message` | 해당 content check 성공 시 메시지 |

## JSON만 바꾸면 되는 경우

| 변경 내용 | JSON 수정만으로 가능 |
| --- | --- |
| 폴더명이 조금 달라짐 | `folder_keyword_chain` 변경 |
| 파일명 키워드가 바뀜 | `filename_keywords` 변경 |
| 프로젝트번호 대신 제품명/PL/WD를 파일명에 넣어야 함 | `{product}`, `{pl}`, `{wd}` 플레이스홀더 사용 |
| 확장자를 제한하거나 풀어야 함 | `extensions` 변경 |
| 1개가 아니라 N개 이상 허용 | `exact_count` 제거 후 `min_count` 사용 |
| docx 표 label명이 바뀜 | content check의 `label` 변경 |
| PDF label 주변 검색 범위를 늘림 | `line_window` 변경 |
| 날짜 형식 허용 범위가 바뀜 | `regex` 변경 |
| 사용자 메시지를 바꿈 | `missing_message`, `multiple_message`, `pass_message`, `failure_message` 변경 |
| 규칙을 잠시 끔 | `enabled=False` |

## 코드 수정이 필요한 경우

| 변경 내용 | 필요한 작업 |
| --- | --- |
| 새로운 문서 형식 검사 | `ecm_download_review_inspection.py`에 parser/check type 추가 |
| Excel 내부 셀 값을 읽어야 함 | xlsx/xls reader 구현과 테스트 추가 |
| 이미지/OCR 기반 검사 | OCR 또는 이미지 분석 경로 설계 필요 |
| 여러 표/여러 페이지에서 의미 기반 비교 | 새 content check type 추가 |
| ECM 다운로드 흐름 변경 | `03_webpage1_automation.md`, `04_agent_download.md` 기준으로 자동화 코드 수정 |
| UI 결과 표시 형식 변경 | `08_ui_api_design.md`와 프론트 코드 수정 |

## 수정 절차

### 1. 현재 규칙 확인

```powershell
.\.venv\Scripts\python.exe manage.py shell --settings=myproject.ui_mock_settings -c "from main.models import DownloadReviewRule; import json; [print(r.code, r.name, r.rule_type, r.enabled, json.dumps(r.config_json, ensure_ascii=False)) for r in DownloadReviewRule.objects.order_by('sort_order')]"
```

### 2. DB 백업

`workflow.db`는 로컬 실행 DB라 Git에 올리지 않는다. 직접 바꾸기 전에는 백업한다.

```powershell
Copy-Item main\data\workflow.db "main\data\workflow.db.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

### 3. 기본 규칙을 코드로 관리하는 경우

기본 규칙은 `main/management/commands/seed_download_review_rules.py`의 `_actual_rule_spec()`에서 관리한다.

수정 후 dry-run으로 반영 내용을 본다.

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
```

문제가 없으면 실제 DB에 반영한다.

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

### 4. 로컬 DB만 임시 수정하는 경우

긴급 확인용으로 로컬 `workflow.db`만 바꿀 수 있다. 다만 반복해서 쓸 변경이면 seed 명령의 기본 규칙도 같이 수정해야 한다.

예시는 `artifact_01`의 계약서 파일명 키워드만 바꾸는 명령이다.

```powershell
.\.venv\Scripts\python.exe manage.py shell --settings=myproject.ui_mock_settings -c "from main.models import DownloadReviewRule; r=DownloadReviewRule.objects.get(code='artifact_01'); c=dict(r.config_json); c['filename_keywords']=['계약서','{project_number}']; r.config_json=c; r.save(update_fields=['config_json','updated_at'])"
```

### 5. 검증

```powershell
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --dry-run --settings=myproject.ui_mock_settings
git diff --check
```

샘플 zip 검증 기준은 `C:\test` 경로와 프로젝트 번호 `TTA-26-00266`이다. 현재 1~5번 실제 규칙은 이 샘플 기준으로 모두 통과한 상태다.

## 자주 하는 수정 예시

### 파일명이 `합의서`에서 `시험합의서`로 바뀌는 경우

```json
{
  "filename_keywords": ["시험합의서", "{project_number}"]
}
```

### 파일명에 WD도 포함되어야 하는 경우

```json
{
  "filename_keywords": ["계약서", "{project_number}", "{WD}"]
}
```

`{WD}` 값은 Google Sheet F열에서 `ecm_list.WD`로 들어온다. 값이 비어 있으면 해당 키워드는 검사에서 빠진다.

### 날짜 형식을 더 엄격하게 하는 경우

```json
{
  "type": "docx_next_paragraph_matches",
  "after_text": "({project_number}) 품질특성별 시험대상제품 정보 기재사항",
  "regex": "^\\d{4}\\.\\d{2}\\.\\d{2}\\.$",
  "remove_whitespace": true,
  "failure_message": "1페이지 날짜가 yyyy.mm.dd. 형식이 아닙니다."
}
```

## 주의사항

- `config_json.artifact_column`은 `ecm_list`의 산출물 컬럼명과 정확히 맞아야 write-back 된다.
- `filename_keywords`는 모든 키워드가 파일명에 포함되어야 한다.
- `folder_keyword_chain`은 첫 번째로 조건을 만족한 폴더를 선택한다. 같은 조건의 폴더가 여러 개라면 실제 샘플로 확인해야 한다.
- 사용자에게 표시되는 경로는 서버 절대 경로가 아니라 프로젝트 번호가 포함된 상대적 표시 경로를 우선 사용한다.
- 직접 DB를 수정한 내용은 seed 명령을 다시 실행하면 덮일 수 있다.
- JSON으로 표현하기 어려운 새 검사 방식은 새 `rule_type` 또는 새 `content_check` 타입으로 구현한다.
