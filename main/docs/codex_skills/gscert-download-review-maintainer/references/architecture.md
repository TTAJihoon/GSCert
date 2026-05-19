# Architecture Reference

## Main Surfaces

- UI template: `main/templates/review/ecm_download_review.html`
- UI script: `main/static/scripts/review/ecm_download_review.js`
- UI style: `main/static/css/review/ecm_download_review.css`
- API wrappers: `main/views/review/ecm_download_review_api.py`
- Job logic: `main/views/review/ecm_download_review_jobs.py`
- Center definitions: `main/views/review/ecm_download_review_centers.py`
- Reference DB access/write-back: `main/views/review/ecm_reference_db.py`
- Worker: `main/views/review/ecm_download_review_worker.py`
- ECM automation: `main/views/review/ecm_download.py`
- Windows popup automation: `main/views/review/ecm_agent_popup.py`
- Download verification: `main/views/review/ecm_download_verify.py`
- Inspection execution: `main/views/review/ecm_download_review_inspection.py`

## DB Split

- `main/data/ecmlist.db`: Sangam project list and latest review summary.
- `main/data/ecmlist2.db`: Yeongnam project list and latest review summary.
- `main/data/workflow.db`: job/project/rule/result/log/lock history.

`ecmlist*.db` is the latest dashboard source. `workflow.db` is the durable evidence source.

## Center Behavior

- UI center tabs: `sangam`, `yeongnam`.
- Center tabs filter:
  - `GET /api/projects/?center=sangam|yeongnam`
  - `GET /api/jobs/?center=sangam|yeongnam`
- Center tabs do not filter:
  - `GET /api/jobs/active/`

The worker and current job are global because the server and ECM automation resource are shared.

## API Contract

- Reads use `GET`.
- State changes use `POST`.
- Responses are JSON.
- Responses set `Cache-Control: no-store`.
- `POST /api/jobs/` validates selected project numbers against the selected center DB.
- Active/queued/scheduled duplicate projects are rejected per center.
- Completed projects are rejected as invalid/bug-bypass requests.
- Job queue limit is 5 active jobs.

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

