param(
    [switch]$Replace
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
$serviceScript = Join-Path $repoRoot 'main\windows_services\server_time_control_service.py'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "가상환경 Python을 찾을 수 없습니다: $pythonPath"
}
if (-not (Test-Path -LiteralPath $serviceScript -PathType Leaf)) {
    throw "서비스 스크립트를 찾을 수 없습니다: $serviceScript"
}

$existing = Get-Service -Name 'GSCertTimeControl' -ErrorAction SilentlyContinue
if ($existing -and -not $Replace) {
    throw 'GSCertTimeControl 서비스가 이미 있습니다. 갱신하려면 -Replace를 지정하세요.'
}

Push-Location $repoRoot
try {
    if ($existing) {
        if ($existing.Status -ne 'Stopped') {
            Stop-Service -Name 'GSCertTimeControl' -ErrorAction Stop
        }
        & $pythonPath $serviceScript --startup auto update
    } else {
        & $pythonPath $serviceScript --startup auto install
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows 서비스 설치/갱신에 실패했습니다.'
    }
    sc.exe failure GSCertTimeControl reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows 서비스 복구 정책 설정에 실패했습니다.'
    }
    Start-Service -Name 'GSCertTimeControl'
    Get-Service -Name 'GSCertTimeControl' | Select-Object Name, Status, StartType
} finally {
    Pop-Location
}
