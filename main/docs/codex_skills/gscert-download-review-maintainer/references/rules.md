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

Implemented real artifact rules:

- 1번 계약서
- 2번 합의서
- 3번 수수료산정표
- 4번 시험환경구성도
- 5번 품질특성별제품정보기재사항

Rule details are stored in `inspection_rule.config_json`, including folder keyword chains,
file-name keywords, extension counts, labels, expected values, regexes, and user-facing messages.

Use this command to seed only implemented real rules:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --only-real --enable --update-existing --settings=myproject.ui_mock_settings
```

Prefer extending the inspection engine with small, explicit rule types rather than placing complex logic directly in the worker.

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
- Treat `warning` as "manual review needed"; do not write it as `O/X` in `ecmlist.db`.
- When LLM API is later connected, add a provider adapter rather than changing rule storage or UI contracts.

## Rule Implementation Checklist

1. Add or update rule evaluation code in `ecm_download_review_inspection.py`.
2. Ensure each result has user-friendly `expected`, `actual`, and `message`.
3. Keep internal details in `raw_detail_json` or admin logs.
4. Map one actual rule to one `ecmlist.db` artifact column when applicable.
5. Add focused tests in `main/tests.py`.
6. Update `main/docs/05_zip_inspection.md`, `08_ui_api_design.md`, and `00_next_step.md` when behavior changes.

