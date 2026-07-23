# Rules Reference

## Rule Storage

Rules live in shared PostgreSQL `reference` DB through `DownloadReviewRule` (`inspection_rule`):

- `code`
- `name`
- `target_file_pattern`
- `target_file_type`
- `rule_type`
- `config_json`
- `severity`
- `enabled`
- `version`
- `sort_order`

Rule results live in local `workflow.db` through `DownloadReviewRuleResult` (`inspection_result`). Store both pass and fail results for every rule executed. Because rules and results are in different DBs, results keep denormalized `rule_code` and `rule_name` instead of an FK.

## Canonical Rule Manual

The source of truth for artifact rules is:

```text
main/docs/03_inspection_rule_manual.md
```

That document manages every rule from 1 through 18. When a new rule is discussed, update the manual first, then implement code and seed changes.

Current rule status:

| No. | Rule | Status | Artifact column |
| --- | --- | --- | --- |
| 1 | 계약서 | implemented | `계약서` |
| 2 | 합의서 | implemented | `합의서(PDF)` |
| 3 | 수수료산정표 | implemented | `수수료산정표` |
| 4 | 시험환경구성도 | implemented | `시험환경구성도` |
| 5 | 품질특성별제품정보기재사항 | implemented | `품질특성별제품정보기재사항` |
| 6 | 기능리스트 | implemented | `기능리스트` |
| 7 | 시험계획서 | implemented | `시험계획서(PDF)` |
| 8 | 제품 스크린샷 | implemented | `최초/최종형상RawData` |
| 9 | 테스트케이스 | implemented | `테스트케이스` |
| 10 | 결함리포트 | implemented | `결함리포트` |
| 11 | 점검표 | implemented | `점검표(PDF)` |
| 12 | 1차/2차/성능/보안RawData | implemented | `1차/2차/성능/보안RawData` |
| 13 | 시험성적서 | implemented | `시험성적서(PDF)` |
| 14 | 시험기록서 | implemented | `시험기록서` |
| 15 | 품질평가보고서 | implemented | `품질평가보고서` |
| 16 | 품질검사표 | implemented | `품질검사표` |
| 17 | SW저작권확인서 | implemented | `SW저작권확인서` |
| 18 | 홍보이미지 | implemented | `홍보이미지` |

## Shared Placeholders

- `{project_number}`, `{프로젝트번호}`: project number
- `{product}`, `{제품명}`: product name after removing the parsed version
- `{company}`, `{회사명}`: company name
- `{버전}`: version parsed from product name; if no version prefix exists, use the final whitespace-delimited token; if no whitespace exists, treat version as missing
- `{pl}`, `{PL}`: 시험PL
- `{wd}`, `{WD}`: WD
- `{시작일}`, `{종료일}`: `reference_project.start_date` and `reference_project.expected_end_date`, exposed through the project metadata API
- `{연도}`: `20YY` parsed from `TTA-YY-xxxxx`
- `{잔여결함수}`: residual defect count produced by rule 10 결함리포트
- `{결함차수}`: defect report round count produced by rule 13 시험성적서
- `{1차}`, `{2차}`, etc.: defect report dates by round, parsed from the `결함리포트 송부` table in rule 13 시험성적서
- `{H}`: High defect count produced by rule 10 결함리포트
- `{R}`: 수정전 defect count produced by rule 10 결함리포트
- `{측정항목별점수표}`: D7:D90 values from rule 11 점검표
- `{품질부특성측정값}`: quality sub-characteristic values produced by rule 16 품질검사표
- `{신청일}`: H column from the connected Google Sheet row matched by `{프로젝트번호}`
- `{계약일}`: I column from the connected Google Sheet row matched by `{프로젝트번호}`
- `{인증위}`: `reference_project.cert_date` or normalized committee date matched by `{프로젝트번호}`

Rules can publish derived variables by storing them in `raw_detail_json.variables`. Later rules in the same inspection run can resolve them through `{변수명}` placeholders, so seed `sort_order` must keep producer rules before consumer rules. Rule 13 시험성적서 is intentionally seeded with `sort_order=95` so it runs before rule 7 시험계획서 at `sort_order=96` and rule 10 결함리포트 at `sort_order=100`; rule 9 테스트케이스 is seeded with `sort_order=105` so it runs after rule 10 and can consume `{잔여결함수}`; rule 16 품질검사표 is seeded with `sort_order=145` so it runs before rule 15 품질평가보고서 at `sort_order=150`.

## Center-Based Expected Names

Rules 7, 9, and 11 use center-specific expected names for 시험계획서 담당자, 테스트케이스 검토자, and 점검표 표지 검토자:

| Center code | Expected name |
| --- | --- |
| `bundang` | `임우섭` |
| `sangam` | `김진영` |
| `yeongnam` | `이재훈` |
| default | `김진영` |

## Draft Rules

Draft rules are test scaffolding created by:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --settings=myproject.ui_mock_settings
```

Default behavior:

- creates rules from `ARTIFACT_REVIEW_COLUMNS`
- leaves them disabled unless `--enable` is passed
- uses `version=draft-1`

Policy:

- Keep draft rules while no real rule exists for that artifact column.
- When a real rule is implemented for a column, delete or disable the matching draft rule.
- Avoid running draft and real rules for the same artifact column at the same time.

## Review Result Meaning

Project review:

- all rules pass: `completed`, `reference_project.review_result=O`
- at least one rule fails: `needs_fix`, `reference_project.review_result=X`
- download/source/analysis failure: held/failed in workflow only; do not write rule `O/X` as a successful inspection result

Artifact columns:

- pass: `O`
- fail: `X`
- not executed / no target: empty string

## Existing Rule Types

Check `main/views/review/ecm_download_review_inspection.py` before adding a new type.

Current useful patterns include:

- required file count
- required file name contains
- required file extension
- file name contains project number
- all files non-empty
- required artifact file (`required_artifact_file`)
- document artifact check (`document_artifact_check`)
- feature list Excel check (`excel_feature_list_check`)
- test plan document check (`test_plan_document_check`)
- screenshot image folder date check (`image_screenshot_folder_date_check`)
- test case Excel check (`test_case_check`)
- rawdata folder structure check (`rawdata_folder_structure_check`)
- test report document check (`test_report_document_check`)
- defect report check (`defect_report_check`)
- inspection checklist check (`inspection_checklist_check`)
- quality inspection table check (`quality_inspection_table_check`)
- quality evaluation report check (`quality_evaluation_report_check`)

Rule details are stored in `inspection_rule.config_json`, including folder keyword chains, file-name keywords, extension counts, labels, expected values, regexes, and user-facing messages.

The shared engine version is currently `0.2.0`, and the rulebase manifest/bundle exposes `engine_min_version=0.2.0`. The local Windows app must refuse a rulebase that requires a newer engine than the bundled `gscert_review_core.ENGINE_VERSION`.

Use this command to seed only implemented real rules:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

Prefer extending the inspection engine with small, explicit rule types rather than placing complex logic directly in the worker.

## Pending Rule Notes

- Rule 2 합의서 stores the PDF first page as an artifact button in addition to `.docx/.pdf` file, project-number, Word header `{프로젝트번호}`, and Word footer `TIS-0101-3 (00)` checks.
- Rule 6 기능리스트 is implemented for `.xls/.xlsx`, requires one sheet, checks `{프로젝트번호} 기능리스트`, checks `{PL}` in the same cell as `작성자`, stores the `대분류` capture target range metadata, and renders that range as an Excel-area image artifact.
- Rule 7 시험계획서 is implemented. It uses Word plus PDF, checks the first and second tables, applies the center-specific manager expected name, checks `형상항목 ID`, checks the `WD` schedule column, compares version numbers while tolerating `v`/`ver` prefixes, checks exact footer text `Copyright {연도} TTA`, forbids footer terms `TIS-`, `TPG`, `TIS`, and `소프트웨어시험인증연구소`, stores a PDF first-page image, and compares its `<세부사양>` table with rule 13's `시험성적서_세부사양표` after removing whitespace and newlines from each cell.
- Rule 8 제품 스크린샷 is implemented. It searches under the `설계` folder for a parent folder with at least two child image folders. Candidate child folders must each contain at least five `.png/.jpg/.jpeg/.bmp/.gif` files. Image dates use zip entry modified timestamps, inclusive from `{시작일}` through `{종료일}`.
- Rule 9 테스트케이스 is implemented. It uses `.xls/.xlsx`, requires one sheet, checks `{프로젝트번호} 테스트케이스`, checks an author cell containing `작성자:` and `{PL}`, checks the cell below for `검토자:` and the center-specific reviewer expected name, checks `작성일: {시작일} ~ {종료일}` after removing spaces, forbids header term `TTA`, forbids footer terms `TPG`, `TIS`, and `소프트웨어시험인증연구소`, requires footer term `TTA`, and compares `F` count in the `상세 테스트 결과` column against `{잔여결함수}` from rule 10.
- Rule 10 결함리포트 is implemented. It searches under the `수행` folder for versioned defect report Excel files named with `{프로젝트번호}`, `결함리포트`, and `vN.0`; requires exactly `{결함차수}+1` files; checks exact cumulative sheet sets; forbids `프로젝트번호` in all sheet headers and `소프트웨어시험인증연구소` in all sheet footers; compares `시험환경` across sheets; validates project/sheet/report-date text; and produces `{잔여결함수}`, `{H}`, and `{R}`. If the file count is higher or lower than `{결함차수}+1`, the user-facing message is `시험성적서의 결함 차수와 결함리포트 개수가 다름`.
- Rule 11 점검표 is implemented. It searches under the `설계` folder for one 점검표 Excel file plus exactly one PDF, checks every sheet header, requires footer term `한국정보통신기술협회`, forbids footer terms `TIS-`, `TPG`, `TIS`, and `소프트웨어시험인증연구소`, checks 표지 title/date/center-specific reviewer and `{PL}` author, checks 기능별 점검표 required cells, compares 기능적합성 tables, checks WD, captures the first matched PDF first page, stores `{측정항목별점수표}`, and compares reliability defect counts with `{H}` and `{R}` from rule 10.
- Rule 12 rawdata is implemented. It checks `수행` folder subfolders for 결함, 보안, and 성능 rawdata structures. 결함 requires at least one image, 보안 requires at least two child folders with entries (or a file name containing `보안성`), and 성능 requires at least one entry.
- Rule 13 시험성적서 is implemented. It checks `.docx/.pdf` under `시험 > 종료`, captures the PDF first page as an artifact, stores the first table nearest after `<세부사양>` as both `raw_detail_json.spec_table` and variable `{시험성적서_세부사양표}` for rule 7 comparison, and parses the `결함리포트 송부` table for `{1차}`, `{2차}`, optional later rounds, and `{결함차수}`.
- Rule 14 시험기록서 searches the whole inspection target for a PDF with file name containing `기록서`; it checks existence only and stores the first page as an image artifact. Missing file message: `시험기록서 파일을 찾을 수 없습니다`.
- Rule 15 품질평가보고서 is implemented. It checks one Word file under `인증관련`, validates project number count, signatures, company, 신청일/계약일/시험기간/인증위 dates, and compares the quality table values with `{품질부특성측정값}` from rule 16. `NA`/`N/A` values require the right-hand cell to be `해당사항 없음`.
- Rule 16 품질검사표 is implemented. It checks a single-sheet Excel file named `{프로젝트번호} 품질검사표`, compares D4:D87 with `{측정항목별점수표}`, forbids footer terms `TPG`, `TIS`, and `소프트웨어시험인증연구소`, requires footer term `한국정보통신기술협회`, and produces `{품질부특성측정값}` from E4:E85 by extracting 33 real values, excluding the 27th value, and reordering them as `4~26, 28~33, 1~3`.
- Rule 17 SW저작권확인서 is implemented and checks for a 확인서 PDF under `인증관련`; project number is not required in the file name. It has separate folder-missing, file-missing, and extension-mismatch messages.
- Rule 18 홍보이미지 is implemented and checks for at least one file under a `홍보` folder; file names containing `예시` fail. The current seed does not restrict image extensions.

## LLM Review Interface

LLM-based inspection is prepared as an interface only. It is not yet wired into the worker's automatic rule execution.

Current files:

- `main/views/review/ecm_llm_review.py`
- `main/management/commands/build_llm_review_prompt.py`
- `main/docs/archive/2026-07-doc-cleanup/17_llm_review_interface.md`

Use `build_llm_review_prompt` to create a provider-neutral JSON payload for manual Codex/LLM testing:

```powershell
.\.venv\Scripts\python.exe manage.py build_llm_review_prompt --settings=myproject.ui_mock_settings --project-number TTA-26-00200 --download-dir "C:\Users\jh910\Downloads\TTA-26-00200" --rule-name "계약서 내용 확인" --rule-prompt "계약서에 프로젝트번호와 회사명이 기준정보와 일치하게 기재되어 있는지 확인하세요."
```

Policy:

- Keep simple file existence/name/extension checks as deterministic program rules.
- Use LLM only for rules that require document-text interpretation.
- Do not add real API calls until provider, endpoint, key storage, timeout, retry, logging, and masking policies are decided.
- Treat `warning` as manual review needed; do not write it as a normal `O/X` artifact result.
- When LLM API is later connected, add a provider adapter rather than changing rule storage or UI contracts.

## Rule Implementation Checklist

1. Update `main/docs/03_inspection_rule_manual.md`.
2. Add or update rule evaluation code in `ecm_download_review_inspection.py`.
3. Ensure each result has user-friendly `expected`, `actual`, and `message`.
4. Keep internal details in `raw_detail_json` or admin logs.
5. Map one actual rule to one artifact result key when applicable (`reference_project.artifact_results_json`, with legacy `ecm_list` compatibility where enabled).
6. Add focused tests.
7. Update `main/docs/00_next_step.md` with only the immediate next work.
