# GSCert Local Review App

Windows desktop app package for local ECM submission inspection.

This folder is intentionally separated from the Django server package so the desktop app can be installed and packaged independently.

## Current Scope

- Select a local inspection folder.
- Infer a project number from the folder or file names.
- Fetch project metadata from the Django server API.
- Scan local files and show a file summary.
- Provide a packaging script for Windows `.exe` builds.

The full rule engine will be connected in the next implementation step. The app structure is already prepared so that the local runner can call the shared inspection engine without mixing desktop-only packaging files into the server deployment.

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
