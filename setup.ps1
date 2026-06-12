<#
.SYNOPSIS
  GSCert 초기 환경 설정 — 새 서버에서 최초 1회 실행.
  Python, Git, VC++ Redist, nginx 설치 + 가상환경 구성 + DB 마이그레이션 + 바탕화면 단축아이콘 생성까지 일괄 처리.
.PARAMETER InstallAutomation
  pywin32, pywinauto(Windows 자동화) 패키지를 추가 설치하고 Playwright 브라우저를 다운로드한다.
.PARAMETER InstallSearch
  faiss-cpu, sentence-transformers 등 검색 패키지를 추가 설치한다.
#>
param(
    [switch]$InstallAutomation,
    [switch]$InstallSearch
)

$ErrorActionPreference = "Stop"
$RootDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$SetupDir = Join-Path $RootDir "setup"

# ── 헬퍼 ──────────────────────────────────────────────────────────────
function Step($msg)  { Write-Host "`n[....] $msg" -ForegroundColor Cyan }
function OK($msg)    { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[ -- ] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("Path","Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path","User")
    $env:Path = "$machine;$user"
}

function Get-ServerIP {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' } |
           Sort-Object PrefixLength -Descending |
           Select-Object -First 1).IPAddress
    if (-not $ip) { $ip = "localhost" }
    return $ip
}

# ── 배너 ──────────────────────────────────────────────────────────────
Clear-Host
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   GSCert 초기 환경 설정" -ForegroundColor Yellow
Write-Host "   프로젝트 경로: $RootDir" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan

# ══════════════════════════════════════════════════════════════════════
# 1. VC++ Redistributable
# ══════════════════════════════════════════════════════════════════════
Step "VC++ Redistributable 설치 확인"
$vcInstalled = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
if ($vcInstalled) {
    Warn "VC++ Redistributable 이미 설치되어 있습니다."
} else {
    $vcFile = Join-Path $SetupDir "vc_redist.x64.exe"
    if (-not (Test-Path $vcFile)) { Fail "vc_redist.x64.exe 를 setup 폴더에 넣어주세요." }
    Write-Host "       설치 중..."
    Start-Process -FilePath $vcFile -ArgumentList "/install /quiet /norestart" -Wait
    OK "VC++ Redistributable 설치 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 2. Python
# ══════════════════════════════════════════════════════════════════════
Step "Python 설치 확인"
Refresh-Path
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $ver = & python --version 2>&1
    OK "$ver 확인됨 ($($pythonCmd.Source))"
} else {
    $pyFile = Get-ChildItem $SetupDir -Filter "python-*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pyFile) { Fail "python 설치파일(python-*.exe)을 setup 폴더에 넣어주세요." }
    Write-Host "       $($pyFile.Name) 설치 중 (시간이 걸릴 수 있습니다)..."
    Start-Process -FilePath $pyFile.FullName -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    Refresh-Path
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) { Fail "Python 설치 후에도 찾을 수 없습니다. 재부팅 후 다시 시도하세요." }
    OK "Python 설치 완료 ($($pythonCmd.Source))"
}

# ══════════════════════════════════════════════════════════════════════
# 3. Git
# ══════════════════════════════════════════════════════════════════════
Step "Git 설치 확인"
Refresh-Path
$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($gitCmd) {
    $ver = & git --version 2>&1
    OK "$ver 확인됨"
} else {
    # Git for Windows 설치파일: Git-*-64-bit.exe
    $gitFile = Get-ChildItem $SetupDir -Filter "Git-*-64-bit.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $gitFile) {
        Warn "Git 설치파일(Git-*-64-bit.exe)이 setup 폴더에 없습니다."
        Warn "https://git-scm.com/download/win 에서 다운로드 후 setup 폴더에 넣고 다시 실행하세요."
        Warn "Git 없이 계속 진행합니다 (나중에 수동 설치 가능)."
    } else {
        Write-Host "       $($gitFile.Name) 설치 중..."
        Start-Process -FilePath $gitFile.FullName `
            -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /COMPONENTS=`"icons,ext\reg\shellhere,assoc,assoc_sh`"" `
            -Wait
        Refresh-Path
        OK "Git 설치 완료"
    }
}

# ══════════════════════════════════════════════════════════════════════
# 4. nginx 설치 및 설정
# ══════════════════════════════════════════════════════════════════════
Step "nginx 설치 및 설정"
$NginxInstallDir = "C:\nginx-1.29.8"
$NginxSrcDir     = Join-Path $SetupDir "nginx-1.29.8"
$NginxExe        = Join-Path $NginxInstallDir "nginx.exe"
$NginxConf       = Join-Path $NginxInstallDir "conf\nginx.conf"

if (-not (Test-Path $NginxSrcDir)) {
    Fail "setup\nginx-1.29.8 폴더가 없습니다."
}

if (-not (Test-Path $NginxInstallDir)) {
    Write-Host "       $NginxInstallDir 로 복사 중..."
    Copy-Item -Path $NginxSrcDir -Destination $NginxInstallDir -Recurse -Force
    OK "nginx 복사 완료"
} else {
    # conf만 덮어씌워서 업데이트
    Write-Host "       nginx 이미 존재 — conf 업데이트만 수행"
    Copy-Item -Path (Join-Path $NginxSrcDir "conf\nginx.conf") `
              -Destination $NginxConf -Force
}

# nginx.conf 플레이스홀더 치환
$serverIP   = Get-ServerIP
$staticRoot = ($RootDir -replace '\\', '/') + '/staticfiles'
$conf = Get-Content $NginxConf -Raw -Encoding UTF8
$conf = $conf -replace '__SERVER_IP__', $serverIP
$conf = $conf -replace '__STATIC_ROOT__', $staticRoot
# nginx는 UTF-8 BOM을 지원하지 않으므로 BOM 없이 저장
[System.IO.File]::WriteAllText($NginxConf, $conf, [System.Text.Encoding]::ASCII)

OK "nginx.conf 설정 완료 (IP: $serverIP, static: $staticRoot)"

# nginx 시작 태스크 스케줄러 등록 (시스템 부팅 시 자동 시작)
$taskName = "GSCert-nginx"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction -Execute $NginxExe -WorkingDirectory $NginxInstallDir
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
OK "nginx 부팅 자동시작 태스크 등록 완료"

# nginx 즉시 시작
$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($running) {
    # conf가 바뀌었으므로 reload
    & $NginxExe -s reload 2>$null
    OK "nginx conf reload 완료"
} else {
    Start-Process -FilePath $NginxExe -WorkingDirectory $NginxInstallDir -WindowStyle Hidden
    Start-Sleep -Seconds 1
    OK "nginx 시작 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 5. Python 가상환경
# ══════════════════════════════════════════════════════════════════════
Step "Python 가상환경 설정"
$VenvDir    = Join-Path $RootDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"

if (Test-Path $VenvDir) {
    Warn "가상환경 이미 존재: $VenvDir"
} else {
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "가상환경 생성 실패" }
    OK "가상환경 생성 완료"
}

# pip 업그레이드
& $VenvPython -m pip install --upgrade pip --quiet

# ══════════════════════════════════════════════════════════════════════
# 6. 기본 패키지 설치
# ══════════════════════════════════════════════════════════════════════
Step "기본 패키지 설치 (requirements.txt)"
& $VenvPip install -r (Join-Path $RootDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "기본 패키지 설치 실패" }
OK "기본 패키지 설치 완료"

# playwright는 playwright_job Django 앱이 최상위에서 import하므로 항상 설치
Step "playwright 설치 (Django 앱 구동 필수)"
& $VenvPip install "playwright>=1.59,<1.60" --quiet
if ($LASTEXITCODE -ne 0) { Fail "playwright 설치 실패" }
OK "playwright 설치 완료"

# ══════════════════════════════════════════════════════════════════════
# 7. Automation 패키지 (선택)
# ══════════════════════════════════════════════════════════════════════
if ($InstallAutomation) {
    Step "Automation 패키지 설치 (pywin32, pywinauto 등)"
    & $VenvPip install -r (Join-Path $RootDir "requirements-automation.txt")
    if ($LASTEXITCODE -ne 0) { Fail "Automation 패키지 설치 실패" }
    Write-Host "       Playwright 브라우저(chromium) 설치 중..."
    & $VenvPython -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { Fail "Playwright 브라우저 설치 실패" }
    OK "Automation 패키지 설치 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 8. Search 패키지 (선택)
# ══════════════════════════════════════════════════════════════════════
if ($InstallSearch) {
    Step "Search 패키지 설치 (faiss, sentence-transformers 등)"
    & $VenvPip install -r (Join-Path $RootDir "requirements-search.txt")
    if ($LASTEXITCODE -ne 0) { Fail "Search 패키지 설치 실패" }
    OK "Search 패키지 설치 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 9. 정적 파일 수집
# ══════════════════════════════════════════════════════════════════════
Step "정적 파일 수집 (collectstatic)"
& $VenvPython (Join-Path $RootDir "manage.py") collectstatic --noinput
if ($LASTEXITCODE -ne 0) { Fail "collectstatic 실패" }
OK "정적 파일 수집 완료"

# ══════════════════════════════════════════════════════════════════════
# 10. DB 마이그레이션
# ══════════════════════════════════════════════════════════════════════
Step "Django DB 마이그레이션"
& $VenvPython (Join-Path $RootDir "manage.py") migrate
if ($LASTEXITCODE -ne 0) { Fail "마이그레이션 실패 — 위 오류를 확인하세요." }
OK "마이그레이션 완료"

# ══════════════════════════════════════════════════════════════════════
# 11. 바탕화면 단축아이콘 생성
# ══════════════════════════════════════════════════════════════════════
Step "바탕화면 단축아이콘 생성"
$WshShell    = New-Object -ComObject WScript.Shell
$Desktop     = [System.Environment]::GetFolderPath('Desktop')
$ShortcutPath = "$Desktop\GSCert 서버 관리.lnk"
$Shortcut    = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath      = "powershell.exe"
$Shortcut.Arguments       = "-NoExit -ExecutionPolicy Bypass -File `"$RootDir\launcher.ps1`""
$Shortcut.WorkingDirectory = $RootDir
$Shortcut.WindowStyle     = 1
$Shortcut.IconLocation    = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe,0"
$Shortcut.Description     = "GSCert 서버 관리 메뉴"
$Shortcut.Save()
OK "단축아이콘 생성: $ShortcutPath"

# ══════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   환경 설정이 완료되었습니다." -ForegroundColor Green
Write-Host "   launcher에서 '1. start_all'로 서버를 시작하세요." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
