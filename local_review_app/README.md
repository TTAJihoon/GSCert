# GSCert Local Review App

Windows desktop app package for local ECM submission inspection.

This folder is intentionally separated from the Django server package so the desktop app can be installed and packaged independently.

## Current Scope

- Select a local inspection folder.
- Infer a project number from the folder or file names.
- Fetch project metadata from the Django server API.
- Scan local files and show a file summary.
- Download and cache the shared server rulebase.
- Run local file/folder checks and a first set of Word/PDF/Excel document checks.
- Provide a packaging script for Windows `.exe` builds.

Some server-side deep comparison rules are still reported as unsupported in the local app when they require complex cross-document extraction. The app still checks required files first, then clearly separates unsupported deep checks from missing-file failures.

## Install for Development

```powershell
cd local_review_app
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m gscert_local_review
```

The default server URL is `http://127.0.0.1:8000`. It can be changed in the app UI.

## Package

```powershell
.\scripts\package_windows.ps1
```

The executable is created under `local_review_app/dist/`.
