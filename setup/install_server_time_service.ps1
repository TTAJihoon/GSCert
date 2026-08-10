param(
    [switch]$Replace
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
$serviceScript = Join-Path $repoRoot 'main\windows_services\server_time_control_service.py'
$postInstallScript = Join-Path $repoRoot '.venv\Scripts\pywin32_postinstall.py'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "가상환경 Python을 찾을 수 없습니다: $pythonPath"
}
if (-not (Test-Path -LiteralPath $serviceScript -PathType Leaf)) {
    throw "서비스 스크립트를 찾을 수 없습니다: $serviceScript"
}

# pywin32를 pip로만 설치하면 pythonservice.exe가 시스템 계정(LocalSystem)으로 뜰 때
# servicemanager 등 pywin32 확장 모듈을 못 찾아 ModuleNotFoundError로 죽는다.
# pywin32_postinstall이 pywintypes/pythoncom DLL을 System32에 등록해야 해결된다.
if (Test-Path -LiteralPath $postInstallScript -PathType Leaf) {
    & $pythonPath $postInstallScript -install
    if ($LASTEXITCODE -ne 0) {
        throw 'pywin32_postinstall 실행에 실패했습니다.'
    }
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

    # pythonservice.exe는 venv의 site-packages(특히 win32/win32\lib에 흩어진
    # servicemanager 등 pywin32 확장 모듈)를 계정과 무관하게 못 찾는 경우가 있어
    # ModuleNotFoundError로 즉시 죽는다. 서비스 전용 PYTHONPATH를 레지스트리
    # Environment 값으로 등록해 SCM이 프로세스 시작 시 항상 주입하게 한다.
    $sitePackages = Join-Path $repoRoot '.venv\Lib\site-packages'
    $pythonPathEntries = @(
        $sitePackages,
        (Join-Path $sitePackages 'win32'),
        (Join-Path $sitePackages 'win32\lib'),
        (Join-Path $sitePackages 'Pythonwin')
    ) -join ';'
    Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\GSCertTimeControl' `
        -Name 'Environment' -Type MultiString -Value @("PYTHONPATH=$pythonPathEntries")

    Start-Service -Name 'GSCertTimeControl'
    Get-Service -Name 'GSCertTimeControl' | Select-Object Name, Status, StartType
} finally {
    Pop-Location
}
