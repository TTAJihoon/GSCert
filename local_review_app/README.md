# GSCert Local Review App

Windows desktop app package for local ECM submission inspection.

This folder is intentionally separated from the Django server package so the desktop app can be installed and packaged independently.

## Current Scope

- Select a local inspection folder.
- Infer a project number from the folder or file names.
- Fetch project metadata from the Django server API.
- Scan local files and show a file summary.
- Download and cache the shared server rulebase.
- Run checks through the shared `gscert_review_core` engine used by the web review flow.
- Provide a packaging script for Windows `.exe` builds.

Rules whose `rule_type` is not supported by the bundled shared engine are reported as unsupported. Those cases require a program update, not only a rule bundle update.

## Install for Development

```powershell
cd local_review_app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe run_dashboard.py
```

The default server URL is `http://127.0.0.1:8000`. It can be changed in the app UI.

## Package

```powershell
.\scripts\package_windows_dashboard.ps1
```

The executable folder is created under `local_review_app/dist/GSCertLocalReviewDashboard/`.

The packaging script runs `GSCertLocalReviewDashboard.exe --self-check` after the build. This validates that the packaged app can import the shared engine and parser dependencies (`gscert_review_core`, `lxml`, `xlrd`, `PyMuPDF`, `openpyxl`) before the folder is distributed.
