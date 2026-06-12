<#
.SYNOPSIS
  Django runserver와 download_worker를 함께 시작한다.
.PARAMETER Live
  worker를 live 모드로 시작한다. 지정하지 않으면 dry-run으로 실행한다.
#>
param(
    [switch]$Live
)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== nginx 시작 ==="
& (Join-Path $ScriptDir "start_nginx.ps1")

Write-Host ""
Write-Host "=== Django runserver 시작 ==="
& (Join-Path $ScriptDir "start_server.ps1")

Write-Host ""
Write-Host "=== download_worker 시작 ==="
if ($Live) {
    & (Join-Path $ScriptDir "start_worker.ps1") -Live
} else {
    & (Join-Path $ScriptDir "start_worker.ps1")
}
