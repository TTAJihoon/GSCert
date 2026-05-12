<#
.SYNOPSIS
  Uvicorn 서버와 download_worker를 함께 시작한다.
.PARAMETER DryRun
  worker를 --dry-run 모드로 시작한다.
#>
param(
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Uvicorn 서버 시작 ==="
& (Join-Path $ScriptDir "start_server.ps1")

Write-Host ""
Write-Host "=== download_worker 시작 ==="
if ($DryRun) {
    & (Join-Path $ScriptDir "start_worker.ps1") -DryRun
} else {
    & (Join-Path $ScriptDir "start_worker.ps1")
}
