<#
.SYNOPSIS
  nginx를 중지한다.
#>
$ErrorActionPreference = "SilentlyContinue"
$NginxDir = "C:\nginx-1.29.8"
$NginxExe = Join-Path $NginxDir "nginx.exe"

$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if (-not $running) {
    Write-Host "[INFO] nginx가 실행 중이지 않습니다."
    exit 0
}

if (Test-Path $NginxExe) {
    & $NginxExe -s stop 2>$null
    Start-Sleep -Seconds 2
}

Get-Process -Name nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "[OK] nginx 중지 완료"
