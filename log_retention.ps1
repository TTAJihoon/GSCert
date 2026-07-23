<#
.SYNOPSIS
  logs\ 폴더의 서버/워커 재시작 로그를 최근 N개(out/err 쌍 기준)만 남기고 정리한다.
  start_server.ps1 / start_worker.ps1 이 매 시작 시 dot-source 해서 호출한다.
#>

function Invoke-LogRetention {
    param(
        [Parameter(Mandatory = $true)][string]$LogsDir,
        [Parameter(Mandatory = $true)][string]$Prefix,
        [int]$KeepCount = 5
    )

    $outFiles = Get-ChildItem -Path $LogsDir -Filter "${Prefix}_*_out.log" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending

    if ($outFiles.Count -le $KeepCount) { return }

    $toRemove = $outFiles | Select-Object -Skip $KeepCount
    foreach ($file in $toRemove) {
        $ts = $file.BaseName -replace "^${Prefix}_", "" -replace "_out$", ""
        $errFile = Join-Path $LogsDir "${Prefix}_${ts}_err.log"
        Remove-Item $file.FullName -Force -ErrorAction SilentlyContinue
        if (Test-Path $errFile) {
            Remove-Item $errFile -Force -ErrorAction SilentlyContinue
        }
    }
}
