<#
.SYNOPSIS
  nginx access.log/error.log 을 주기적으로 로테이션한다(Windows에는 logrotate가 없음).

.DESCRIPTION
  현재 access.log/error.log 를 타임스탬프 이름으로 옮기고, nginx에 "-s reopen" 신호를
  보내 새 access.log/error.log 를 다시 열게 한다. 그런 다음 보관 개수(-KeepCount)를
  넘는 오래된 로테이션 파일은 지운다.

  Windows 작업 스케줄러에 주 1회 정도로 등록해서 쓴다:
    schtasks /create /tn "GSCert nginx log rotate" /sc weekly /d SUN /st 03:00 `
      /tr "powershell.exe -ExecutionPolicy Bypass -File C:\Claude_GSCert\setup\rotate_nginx_logs.ps1"
#>
param(
    [string]$NginxDir = "C:\nginx-1.29.8",
    [int]$KeepCount = 8
)
$ErrorActionPreference = "Stop"

$LogsDir = Join-Path $NginxDir "logs"
$NginxExe = Join-Path $NginxDir "nginx.exe"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"

foreach ($name in @("access", "error")) {
    $current = Join-Path $LogsDir "$name.log"
    if (-not (Test-Path $current)) { continue }
    $rotated = Join-Path $LogsDir "${name}_${ts}.log"
    Move-Item -Path $current -Destination $rotated -Force
    Write-Host "[OK] $current -> $rotated"
}

# nginx가 새 access.log/error.log 를 다시 열도록 신호를 보낸다(끊김 없이 로그 파일 교체).
$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($running) {
    Start-Process -FilePath $NginxExe -ArgumentList "-s reopen" -WorkingDirectory $NginxDir -Wait -WindowStyle Hidden
    Write-Host "[OK] nginx -s reopen 완료"
} else {
    Write-Host "[WARN] nginx가 실행 중이 아니라 reopen을 건너뜁니다. 다음 시작 시 새 로그 파일이 자동으로 만들어집니다."
}

foreach ($name in @("access", "error")) {
    $rotatedFiles = Get-ChildItem -Path $LogsDir -Filter "${name}_*.log" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending
    if ($rotatedFiles.Count -gt $KeepCount) {
        $toRemove = $rotatedFiles | Select-Object -Skip $KeepCount
        foreach ($file in $toRemove) {
            Remove-Item $file.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] 오래된 로그 삭제: $($file.Name)"
        }
    }
}
