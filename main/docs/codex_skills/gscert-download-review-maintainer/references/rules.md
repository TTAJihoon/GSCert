# Rules Reference

## Rule Storage

Rules live in `workflow.db` through `DownloadReviewRule`:

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

Rule results live in `DownloadReviewRuleResult`. Store both pass and fail results for every rule executed.

## Canonical Rule Manual

The source of truth for artifact rules is:

```text
main/docs/19_inspection_rule_manual.md
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
| 14 | 시험기록서 | spec locked, not implemented | `시험기록서` |
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
- `{시작일}`, `{종료일}`: `reference.db.sw_data` dates matched by `시험번호 = {프로젝트번호}`
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
- `{인증위}`: `ecmlist.db` `인증일자` value matched by `{프로젝트번호}`

Rules can publish derived variables by storing them in `raw_detail_json.variables`. Later rules in the same inspection run can resolve them through `{변수명}` placeholders, so seed `sort_order` must keep producer rules before consumer rules. Rule 13 시험성적서 is intentionally seeded with `sort_order=95` so it runs before rule 7 시험계획서 at `sort_order=96` and rule 10 결함리포트 at `sort_order=100`; rule 9 테스트케이스 is seeded with `sort_order=105` so it runs after rule 10 and can consume `{잔여결함수}`; rule 16 품질검사표 is seeded with `sort_order=145` so it runs before rule 15 품질평가보고서 at `sort_order=150`.

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

- all rules pass: `completed`, `ecmlist.db` `점검결과=O`
- at least one rule fails: `needs_fix`, `ecmlist.db` `점검결과=X`
- download/agent/analysis failure: held/failed in workflow only; do not write rule `O/X` to `ecmlist.db`

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

Use this command to seed only implemented real rules:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

Prefer extending the inspection engine with small, explicit rule types rather than placing complex logic directly in the worker.

## Pending Rule Notes

- Rule 2 합의서 stores the PDF first page as an artifact button in addition to `.docx/.pdf` file and project-number checks.
- Rule 6 기능리스트 is implemented for `.xls/.xlsx`, requires one sheet, checks `{프로젝트번호} 기능리스트`, checks `{PL}` in the same cell as `작성자`, stores the `대분류` capture target range metadata, and renders that range as an Excel-area image artifact.
- Rule 7 시험계획서 is implemented. It uses `.docx` plus `.pdf`, checks the first and second tables, checks `형상항목 ID`, checks the `WD` schedule column, checks exact footer text `Copyright {연도} TTA`, stores a PDF first-page image, and compares its `<세부사양>` table with rule 13's `시험성적서_세부사양표` after whitespace-normalized matrix comparison.
- Rule 8 제품 스크린샷 is implemented. It searches under the `설계` folder for a parent folder with at least two child image folders. Candidate child folders must each contain at least five `.png/.jpg/.jpeg/.bmp/.gif` files. Image dates use zip entry modified timestamps, inclusive from `{시작일}` through `{종료일}`.
- Rule 9 테스트케이스 is implemented. It uses `.xls/.xlsx`, requires one sheet, checks `{프로젝트번호} 테스트케이스`, checks an author cell containing `작성자:` and `{PL}`, checks the cell below for `검토자:` and `김진영`, checks `작성일: {시작일} ~ {종료일}` after removing spaces, and compares `F` count in the `상세 테스트 결과` column against `{잔여결함수}` from rule 10.
- Rule 10 결함리포트 is implemented. It searches under the `수행` folder for versioned defect report Excel files named with `{프로젝트번호}`, `결함리포트`, and `vN.0`; requires exactly `{결함차수}+1` files; checks exact cumulative sheet sets; compares `시험환경` across sheets; validates project/sheet/report-date text; and produces `{잔여결함수}`, `{H}`, and `{R}`. If the file count is higher or lower than `{결함차수}+1`, the user-facing message is `시험성적서의 결함 차수와 결함리포트 개수가 다름`.
- Rule 11 점검표 is implemented. It searches under the `설계` folder for one 점검표 Excel file plus at least one PDF, checks every sheet header, checks 표지 title/date/author, checks 기능별 점검표 required cells, compares 기능적합성 tables, checks WD, captures the first matched PDF first page, stores `{측정항목별점수표}`, and compares reliability defect counts with `{H}` and `{R}` from rule 10.
- Rule 12 rawdata is implemented. It checks `수행` folder subfolders for 결함리포트, 보안, and 성능 rawdata structures. 보안 and 성능 folders must each contain exactly two child folders, and each child must contain at least one item.
- Rule 13 시험성적서 is implemented. It checks `.docx/.pdf` under `시험 > 종료`, captures the PDF first page as an artifact, stores the first table nearest after `<세부사양>` as both `raw_detail_json.spec_table` and variable `{시험성적서_세부사양표}` for rule 7 comparison, and parses the `결함리포트 송부` table for `{1차}`, `{2차}`, optional later rounds, and `{결함차수}`.
- Rule 14 시험기록서 is a PDF under `시험 > 종료` with file name containing `시험기록서` and `{프로젝트번호}`, made downloadable for manual user review. Missing file message: `시험기록서 파일 확인 불가`.
- Rule 15 품질평가보고서 is implemented. It checks one `.docx` under `시험 > 인증관련`, validates project number count, signatures, company, 신청일/계약일/시험기간/인증위 dates, and compares the `<품질특성별 세부 평가결과>` table values with `{품질부특성측정값}` from rule 16. `NA`/`N/A` values require the right-hand cell to be `해당사항 없음`.
- Rule 16 품질검사표 is implemented. It checks a single-sheet Excel file named `{프로젝트번호} 품질검사표`, compares D4:D87 with `{측정항목별점수표}`, and produces `{품질부특성측정값}` from E4:E85 by extracting 33 real values and reordering them as 4-33 then 1-3.
- Rule 17 SW저작권확인서 is implemented and checks for a 확인서 PDF under `인증관련`; project number is not required in the file name.
- Rule 18 홍보이미지 is implemented and checks for at least one image under a `홍보자료` folder.

## LLM Review Interface

LLM-based inspection is prepared as an interface only. It is not yet wired into the worker's automatic rule execution.

Current files:

- `main/views/review/ecm_llm_review.py`
- `main/management/commands/build_llm_review_prompt.py`
- `main/docs/17_llm_review_interface.md`

Use `build_llm_review_prompt` to create a provider-neutral JSON payload for manual Codex/LLM testing:

```powershell
.\.venv\Scripts\python.exe manage.py build_llm_review_prompt --settings=myproject.ui_mock_settings --project-number TTA-26-00200 --download-dir "C:\Users\jh910\Downloads\TTA-26-00200" --rule-name "계약서 내용 확인" --rule-prompt "계약서에 프로젝트번호와 회사명이 기준정보와 일치하게 기재되어 있는지 확인하세요."
```

Policy:

- Keep simple file existence/name/extension checks as deterministic program rules.
- Use LLM only for rules that require document-text interpretation.
- Do not add real API calls until provider, endpoint, key storage, timeout, retry, logging, and masking policies are decided.
- Treat `warning` as manual review needed; do not write it as `O/X` in `ecmlist.db`.
- When LLM API is later connected, add a provider adapter rather than changing rule storage or UI contracts.

## Rule Implementation Checklist

1. Update `main/docs/19_inspection_rule_manual.md`.
2. Add or update rule evaluation code in `ecm_download_review_inspection.py`.
3. Ensure each result has user-friendly `expected`, `actual`, and `message`.
4. Keep internal details in `raw_detail_json` or admin logs.
5. Map one actual rule to one `ecmlist.db` artifact column when applicable.
6. Add focused tests.
7. Update `main/docs/00_next_step.md` with only the immediate next work.
