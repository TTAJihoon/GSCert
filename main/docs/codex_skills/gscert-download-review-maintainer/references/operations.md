# Operations Reference

## Branch And Handoff

- Main working branch: `codex-job-runner-persistence`.
- Keep `main/docs/00_next_step.md` current after each meaningful commit.
- It should contain the latest state and immediate next work, not the full history.

## Server And UI

Local UI URL:

```text
http://127.0.0.1:8000/download-review/
```

Run server:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=myproject.ui_mock_settings --noreload
```

After UI edits, restart the dev server and verify the page. If the previous server is running, stop its Python runserver processes first.

## Worker Commands

Dry-run one job:

```powershell
.\.venv\Scripts\python.exe manage.py run_download_worker --once --dry-run --settings=myproject.ui_mock_settings
```

Live run is available through `run_download_worker --live`, but live ECM/agent automation should be used deliberately.

## Time Window

The old `20:00-07:00` download-review start window is retired and removed. New jobs queue immediately and migration converts legacy scheduled jobs to queued. While temporary server time is active, the worker leaves jobs queued and starts them only after verified time restoration. Do not restore the old window.

Use `main/docs/15_server_time_control_design.md` as the current server-time-control reference.

## ECM Automation Notes

For prompt-to-action mapping, folder traversal rules, and document-list checkbox selection, read `references/ecm_navigation.md`.

Tree roots:

- Sangam: `상암AX센터`, index `ECM_TREE_ROOT_INDEX=1` because the name appears twice.
- Yeongnam: `영남AX센터`, index `ECM_TREE_ROOT_INDEX_YEONGNAM=0`.

Folder path:

```text
{center}AX센터 > {year}년 시험서비스 > 01 GS인증시험(1등급) > project folder
```

Important selectors:

```text
#edm-folder
#main-list-document > table > thead > tr > th.document-list-header-checkbox > input[type=checkbox]
#menu-folder-list-drop
#edm-main-context-menu li[menuevent="saveDocumentsFileAll"]
```

Windows popup/agent handling lives in `main/views/review/ecm_agent_popup.py`.

## Validation Checklist

Run relevant checks:

```powershell
node --check main\static\scripts\review\ecm_download_review.js
.\.venv\Scripts\python.exe manage.py check --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py test main.tests --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py seed_download_review_rules --dry-run --settings=myproject.ui_mock_settings
```

For DB migrations:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --database=workflow --settings=myproject.ui_mock_settings
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.ui_mock_settings
```

For production after pulling code that touches reference tables:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --database=reference --settings=myproject.settings
```

For browser verification, reload `/download-review/` and check the changed interaction directly.

## Full Folder Download Reuse

- UI buttons for ECM full-folder ZIP downloads should open a GET attachment URL directly:
  `GET /api/projects/{project_number}/full-documents-download/?cert_date=...`
- Do not use a `fetch/POST -> JSON download_url -> anchor click` sequence for user-facing download buttons. That pattern waits for server-side preparation before the browser download starts.
- In `main/static/scripts/review/ecm_download_review.js`, reuse `startFullProjectFolderDownload(project)` for download-review UI surfaces.
- The GET endpoint streams the ZIP as ECM files are downloaded. It writes the first ZIP entry header before fetching that file content, so the browser receives the attachment response without waiting for the entire ZIP to be compressed.

