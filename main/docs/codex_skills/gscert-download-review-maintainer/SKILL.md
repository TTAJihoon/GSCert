---
name: gscert-download-review-maintainer
description: Maintain and continue the GSCert download-review feature. Use when working on the GSCert repository's `/download-review/` UI, APIs, workflow.db/ecmlist.db integration, ECM Playwright/Windows-agent automation, worker process, operational scripts, documentation handoff files, or when deciding what remains before implementing real inspection rules.
---

# GSCert Download Review Maintainer

## Quick Start

Use this skill only inside the GSCert repository, especially on the `codex-job-runner-persistence` branch.

Start by reading:

1. `main/docs/00_next_step.md`
2. `main/docs/15_open_decisions.md`
3. The specific reference in this skill that matches the task.

Treat `main/docs/00_next_step.md` as the current handoff, not as a history log. Keep it focused on the latest completed work and immediate next steps.

## Reference Map

- For system shape, DB split, center behavior, APIs, and key files: read `references/architecture.md`.
- For worker, live ECM automation, server restart, validation commands, and git/doc expectations: read `references/operations.md`.
- For ECM tree navigation prompts, folder-path resolution, and document-list checkbox selection: read `references/ecm_navigation.md`.
- For draft rules, real rule transition, rule result storage, and ecmlist write-back expectations: read `references/rules.md`.

## Core Rules

- Keep numbered design documents under `main/docs/`, not the repository root.
- Keep folder `readme.md` files as directory/file guides, not design-history logs.
- Preserve the current split:
  - `ecmlist.db` and `ecmlist2.db`: latest project list and latest review summary.
  - `workflow.db`: job history, project history, logs, inspection rules, and all rule results.
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

- The active worker/current job view is global to the server, not center-specific.
- Center tabs affect project list and job list filtering.
- Sangam uses `main/data/ecmlist.db`; Yeongnam uses `main/data/ecmlist2.db`.
- Test-only start window is currently allowed all day. Restore operation to `20:00-07:00` when live testing ends.
- Draft rules remain as test scaffolding until matching real rules are implemented.

