---
name: gscert-download-review-maintainer
description: Maintain and continue the GSCert download-review feature. Use when working on the GSCert repository's `/download-review/` UI, APIs, reference PostgreSQL/workflow.db integration, ECM HTTP/Playwright artifact sources, worker process, operational scripts, documentation handoff files, or inspection rules.
---

# GSCert Download Review Maintainer

## Quick Start

Use this skill only inside the GSCert repository, especially on the `codex-job-runner-persistence` branch.

Start by reading:

1. `main/docs/00_next_step.md`
2. `main/docs/02_open_decisions.md`
3. The specific reference in this skill that matches the task.

Treat `main/docs/00_next_step.md` as the current handoff, not as a history log. Keep it focused on the latest completed work and immediate next steps.

## Reference Map

- For system shape, DB split, center behavior, APIs, and key files: read `references/architecture.md`.
- For worker, live ECM automation, server restart, validation commands, and git/doc expectations: read `references/operations.md`.
- For ECM tree navigation prompts, folder-path resolution, and document-list checkbox selection: read `references/ecm_navigation.md`.
- For rule storage, real rule execution, result storage, and artifact result write-back expectations: read `references/rules.md`.

## Core Rules

- Keep numbered design documents under `main/docs/`, not the repository root.
- Keep folder `readme.md` files as directory/file guides, not design-history logs.
- Preserve the current split:
  - `reference` PostgreSQL: shared project list, PL mapping, certification history, `inspection_rule`, and `inspection_manual_override`.
  - `workflow.db`: local job history, project processing state, rule results, logs, locks, and similar-analysis jobs.
  - legacy `ecmlist*.db`: compatibility path only when PostgreSQL project source is disabled.
- Keep `GET` for reads and `POST` for state changes.
- Do not expose server absolute paths, screenshots paths, or stack traces in user-facing API/UI responses.
- Restart the local server after UI changes so the user can verify in the browser.
- When committing, update `main/docs/00_next_step.md` with the latest handoff and next action.

## Validation

Use the smallest validation set that covers the touched surface:

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
```

For worker or rule changes, add the relevant command:

```powershell
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --dry-run --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py run_download_worker --once --dry-run --settings=myproject.ui_mock_settings
```

For UI changes, restart the server and verify `/download-review/`.

## Current Important Assumptions

- Active/current job and job history views are global to the server queue and accumulate all centers.
- Center selection in the UI affects only the project list.
- 194 is the main download-review server and handles bundang/sangam/yeongnam through `ecm-http`.
- 241 is not a download-review worker target; it should route download-review traffic back to 194.
- Project/rule data should come from shared PostgreSQL `reference` in normal operation.
- Manual pass overrides are shared business judgments and should stay in PostgreSQL `reference`, not local `workflow.db`.
- The old `20:00-07:00` download-review start window is retired and removed. New jobs queue immediately, but the worker must leave them queued while temporary server time is active and resume only after verified restoration; do not restore the old window.
- Draft rules are compatibility/test scaffolding; use `--only-real` for current implemented 1~18 rules.
