# Architecture Reference

## Main Surfaces

- UI template: `main/templates/review/ecm_download_review.html`
- UI script: `main/static/scripts/review/ecm_download_review.js`
- UI style: `main/static/css/review/ecm_download_review.css`
- API wrappers: `main/views/review/ecm_download_review_api.py`
- Job logic and serializers: `main/views/review/ecm_download_review_jobs.py`
- Center definitions: `main/views/review/ecm_download_review_centers.py`
- Reference DB access/write-back: `main/views/review/ecm_reference_db.py`
- Worker: `main/views/review/ecm_download_review_worker.py`
- Artifact source boundary: `main/views/review/artifact_source.py`
- HTTP ECM client: `main/views/review/ecm_http_client.py`
- Legacy Playwright ECM automation: `main/views/review/ecm_download.py`
- Legacy Windows popup automation: `main/views/review/ecm_agent_popup.py`
- Inspection execution: `main/views/review/ecm_download_review_inspection.py`
- Shared result display: `gscert_review_core/result_display.py`

## DB Split

- `reference` PostgreSQL: shared project list, PL mapping, certification history, `inspection_rule`, and `inspection_manual_override`.
- `workflow` SQLite (`main/data/workflow.db`): server-local jobs, project processing state, `inspection_result`, logs, locks, and similar-analysis jobs.
- `default` SQLite (`db.sqlite3`): Django default tables and legacy `Job`.
- legacy `ecmlist*.db`: compatibility path when `DOWNLOAD_REVIEW_PROJECT_SOURCE` is not `postgres`.

`inspection_rule` and `inspection_result` live in different DBs, so results identify rules with denormalized `rule_code` and `rule_name`. Manual pass overrides are stored in `inspection_manual_override` by `center_code + project_number + rule_code`, so they survive result-row replacement during reinspection.

## Center Behavior

- 194 is the main download-review server.
- 194 handles `bundang`, `sangam`, and `yeongnam` through `ecm-http`.
- 241 is not a download-review processing target; route download-review traffic back to 194.
- Center selection in the UI only filters the project list:
  - `GET /api/projects/?center=bundang|sangam|yeongnam`
- Active/current job and job history views call `GET /api/jobs/` without a center and are global to the server queue, accumulating jobs from every center.
- `GET /api/jobs/?center=...` remains accepted for explicit API diagnostics, but the UI does not use it for the progress/history tabs.

## API Contract

- Reads use `GET`.
- State changes use `POST`.
- Responses are JSON.
- Responses set `Cache-Control: no-store`.
- `POST /api/jobs/` validates selected project numbers against the selected center.
- Active/queued/scheduled duplicate projects are rejected per center.
- Completed projects are rejected as invalid/bug-bypass requests.
- Job queue limit is 5 active jobs.

## Result Display Contract

- Web and Windows app result tables should use `gscert_review_core/result_display.py`.
- Results should expose user-friendly `expected`, `actual`, and `message` values.
- Internal evidence stays in `raw_detail_json` or admin logs.

## User-Facing Data Boundaries

Show:

- project number
- company/product/PL
- review status
- rule status
- user-readable error message
- project-folder-relative paths or file names

Do not show:

- server absolute path
- screenshot path
- internal stack trace
- admin-only raw details
