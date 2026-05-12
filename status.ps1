<#
.SYNOPSIS
  Django runserver와 download_worker의 상태를 표시한다.
#>
$ErrorActionPreference = "SilentlyContinue"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunDir  = Join-Path $RootDir "run"
$Port    = 8000

Write-Host "========== GSCert 상태 =========="
Write-Host ""

# --- Django runserver ---
Write-Host "[Django runserver]"
$serverPidFile = Join-Path $RunDir "django_runserver.pid"
if (Test-Path $serverPidFile) {
    $serverPid = [int](Get-Content $serverPidFile -Raw).Trim()
    $serverProc = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
    if ($serverProc) {
        Write-Host "  PID:    $serverPid (실행 중)"
    } else {
        Write-Host "  PID:    $serverPid (종료됨 - 유령 PID 파일)"
    }
} else {
    Write-Host "  PID:    파일 없음"
}

$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    $ownerPid = ($portInUse | Select-Object -First 1).OwningProcess
    Write-Host "  포트:   $Port 사용 중 (PID $ownerPid)"
} else {
    Write-Host "  포트:   $Port 사용 안 함"
}

Write-Host ""

# --- Worker ---
Write-Host "[download_worker]"
$workerPidFile = Join-Path $RunDir "download_worker.pid"
if (Test-Path $workerPidFile) {
    $workerPid = [int](Get-Content $workerPidFile -Raw).Trim()
    $workerProc = Get-Process -Id $workerPid -ErrorAction SilentlyContinue
    if ($workerProc) {
        Write-Host "  PID:    $workerPid (실행 중)"
    } else {
        Write-Host "  PID:    $workerPid (종료됨 - 유령 PID 파일)"
    }
} else {
    Write-Host "  PID:    파일 없음"
}

Write-Host ""
Write-Host "[workflow.db]"

$WorkflowDb = Join-Path $RootDir "main\data\workflow.db"
if (Test-Path $WorkflowDb) {
    $VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        $VenvPython = Join-Path $RootDir "venv\Scripts\python.exe"
    }
    if (-not (Test-Path $VenvPython)) { $VenvPython = "python" }

    $pyCode = "import sqlite3,os,sys;" +
        "db=r'$WorkflowDb';" +
        "conn=sqlite3.connect(db);c=conn.cursor();" +
        "c.execute(""SELECT id,status,worker_pid,worker_heartbeat_at FROM automation_job WHERE status IN ('scheduled','queued','running') ORDER BY requested_at LIMIT 5"");" +
        "rows=c.fetchall();" +
        "[print(f'  작업 {r[0]}: status={r[1]}, worker_pid={r[2]}, heartbeat={r[3] or chr(45)}') for r in rows] if rows else print('  활성 작업 없음');" +
        "conn.close()"

    & $VenvPython -c $pyCode 2>&1
} else {
    Write-Host "  workflow.db 파일 없음"
}

Write-Host ""
Write-Host "================================="
