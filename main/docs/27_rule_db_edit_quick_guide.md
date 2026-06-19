# 점검규칙 DB 수정 빠른 가이드

## 핵심 요약

점검규칙은 Django 모델 `DownloadReviewRule`로 관리되며, 실제 테이블명은 `inspection_rule`이다.

| 구분 | 값 |
| --- | --- |
| DB alias | `workflow` |
| 개발/현재 SQLite 파일 | `main/data/workflow.db` |
| 규칙 테이블 | `inspection_rule` |
| 결과 테이블 | `inspection_result` |
| seed 코드 | `main/management/commands/seed_download_review_rules.py` |
| 실행 코드 | `main/views/review/ecm_download_review_inspection.py` |
| Windows 앱 배포 API | `/api/local-review/rules/manifest/`, `/api/local-review/rules/bundle/` |

PostgreSQL로 전환해도 앱이 보는 구조는 같다. DB 종류만 SQLite에서 PostgreSQL로 바뀌고, 테이블명과 컬럼 구조는 Django 모델 기준으로 유지된다.

## 규칙 저장 형태

`inspection_rule`의 주요 컬럼은 다음과 같다.

| 컬럼 | 실무 의미 | 수정 빈도 |
| --- | --- | --- |
| `code` | 규칙 고유 코드. 예: `artifact_01` | 거의 수정 금지 |
| `name` | 화면에 보이는 규칙명 | 필요 시 수정 |
| `target_file_type` | 대표 파일 유형. 예: `pdf`, `xlsx`, `any` | 가끔 수정 |
| `rule_type` | 어떤 검사 로직을 쓸지 지정 | 신중히 수정 |
| `config_json` | 파일명 키워드, 확장자, 개수, 기대값, 메시지 등 실제 조건 | 가장 자주 수정 |
| `severity` | 보통 `error` | 거의 고정 |
| `enabled` | 규칙 사용 여부 | 자주 수정 가능 |
| `version` | 규칙 버전 문자열. 예: `actual-1` | 필요 시 수정 |
| `sort_order` | 실행/표시 순서 | 필요 시 수정 |
| `updated_at` | 수정 시 자동 갱신 | 직접 수정하지 않음 |

실제 작업은 대부분 `enabled`, `sort_order`, `config_json` 수정이다.

## 예시 1: 계약서 규칙

`artifact_01` 계약서 규칙은 PDF 파일 1개가 있어야 통과한다.

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

해석:

| 항목 | 의미 |
| --- | --- |
| `filename_keywords` | 파일명 또는 경로에 `계약서`와 프로젝트번호가 모두 포함되어야 함 |
| `extensions` | `.pdf`만 인정 |
| `exact_count` | 정확히 1개 필요 |
| `missing_message` | 실패 시 사용자에게 보여줄 메시지 |
| `pass_message` | 성공 시 저장할 메시지 |

## 예시 2: 시험환경구성도 규칙

PNG 또는 PPTX 중 1개 이상 있으면 통과한다.

```json
{
  "artifact_column": "시험환경구성도",
  "folder_keyword_chain": ["시험", "계획"],
  "filename_keywords": ["구성도", "{project_number}"],
  "extensions": [".png", ".pptx"],
  "min_count": 1,
  "missing_message": "파일이 없습니다.",
  "pass_message": "시험환경구성도 파일을 확인했습니다."
}
```

파일명을 완화하려면 보통 `filename_keywords`만 수정한다. 예를 들어 프로젝트번호 조건을 빼고 싶으면 다음처럼 바꾼다.

```json
"filename_keywords": ["구성도"]
```

## 예시 3: 합의서 Word/PDF 규칙

Word 1개와 PDF 1개가 있어야 하고, 문서 안의 시험신청번호도 확인한다.

```json
{
  "artifact_column": "합의서(PDF)",
  "filename_keywords": ["합의서", "{project_number}"],
  "required_files": [
    {"extensions": [".docx", ".docm"], "exact_count": 1},
    {"extensions": [".pdf"], "exact_count": 1}
  ],
  "content_checks": [
    {
      "type": "docx_table_next_cell_equals",
      "extensions": [".docx", ".docm"],
      "label": "시험신청번호",
      "expected": "{project_number}",
      "failure_message": "프로젝트 번호가 맞지 않습니다."
    }
  ],
  "missing_message": "필요한 합의서 파일이 없습니다."
}
```

해석:

| 항목 | 의미 |
| --- | --- |
| `required_files` | 확장자별 필수 파일 개수 |
| `content_checks.type` | 문서 내부 검사 방식 |
| `label` | 문서에서 찾을 항목명 |
| `expected` | 기대값. `{project_number}`는 실행 시 실제 프로젝트번호로 치환 |
| `failure_message` | 내부 값이 다를 때 보여줄 메시지 |

## 실제 수정 방법

### 권장: seed 코드 수정 후 반영

규칙 변경은 DB를 직접 고치기보다 `seed_download_review_rules.py`를 수정하고 seed 명령으로 반영하는 방식이 가장 안전하다.

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --dry-run --settings=myproject.ui_mock_settings
```

dry-run 결과가 맞으면 실제 반영:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

장점:

- Git에 규칙 변경 이력이 남는다.
- 운영/개발 DB를 같은 정의로 다시 만들 수 있다.
- 실수로 `code`, `rule_type`을 잘못 바꾸는 일을 줄일 수 있다.

### 긴급: DB 직접 수정

운영에서 즉시 끄거나 메시지만 바꾸는 정도는 DB 직접 수정도 가능하다.

규칙 조회:

```sql
SELECT code, name, rule_type, enabled, version, sort_order, config_json
FROM inspection_rule
ORDER BY sort_order, name;
```

규칙 비활성화:

```sql
UPDATE inspection_rule
SET enabled = 0
WHERE code = 'artifact_07';
```

SQLite에서는 `enabled`가 `0/1`이고, PostgreSQL에서는 보통 `false/true`로 쓴다.

## 수정 전 확인할 정보

규칙을 고치기 전에 아래만 정하면 된다.

| 확인할 것 | 예시 |
| --- | --- |
| 어떤 산출물인가 | 계약서, 합의서, 결함리포트 |
| 규칙 코드 | `artifact_01` |
| 파일명 조건 | `["계약서", "{project_number}"]` |
| 확장자 | `[".pdf"]`, `[".docx", ".docm"]` |
| 필요한 개수 | `exact_count: 1` 또는 `min_count: 1` |
| 내부 값 검사 여부 | Word 표, PDF 1페이지, Excel 시트 등 |
| 실패 메시지 | 사용자가 바로 고칠 수 있는 문장 |
| 웹/Windows 앱 둘 다 적용 가능한가 | 새 `rule_type`이면 프로그램 업데이트 필요 |

## 반영 후 확인

1. 서버 규칙 API 확인

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/local-review/rules/manifest/"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/local-review/rules/bundle/"
```

2. Windows 앱에서 `규칙 업데이트` 클릭

3. 테스트 폴더 선택 후 `점검 실행`

4. 서버 검증

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
```

## 주의사항

- `code`는 결과 매핑과 이력 식별에 쓰이므로 가급적 바꾸지 않는다.
- `rule_type`을 바꾸면 실행 코드가 해당 유형을 지원해야 한다.
- `config_json`은 JSON 문법 오류가 나면 규칙 실행이 실패한다.
- 기존 `rule_type`에서 키워드/확장자/개수/메시지만 바꾸는 경우는 Windows 앱 재배포 없이 규칙 업데이트로 반영된다.
- 새 검사 로직이나 새 문서 파서가 필요하면 서버 코드 배포와 Windows 앱 업데이트가 필요하다.
