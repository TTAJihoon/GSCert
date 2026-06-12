<#
.SYNOPSIS
  download_worker와 Uvicorn 서버를 함께 중지한다.
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== download_worker 중지 ==="
& (Join-Path $ScriptDir "stop_worker.ps1")

Write-Host ""
Write-Host "=== Django 서버 중지 ==="
& (Join-Path $ScriptDir "stop_server.ps1")

Write-Host ""
Write-Host "=== nginx 중지 ==="
& (Join-Path $ScriptDir "stop_nginx.ps1")
