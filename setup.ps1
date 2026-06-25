<#
.SYNOPSIS
  GSCert 초기 환경 설정 — 새 서버에서 최초 1회 실행.
  Python, Git, VC++ Redist, nginx, LibreOffice 다운로드·설치 + 가상환경 구성 + DB 마이그레이션 + 바탕화면 단축아이콘 생성까지 일괄 처리.
  각 설치파일이 setup\ 폴더에 이미 있으면 다운로드를 건너뛰고 로컬 파일을 사용한다.
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
$RootDir  = "C:\Claude_GSCert"
$SetupDir = Join-Path $RootDir "setup"

if (-not (Test-Path $RootDir)) {
    Write-Host "[FAIL] 설치 경로가 없습니다: $RootDir" -ForegroundColor Red
    Write-Host "       먼저 저장소를 복제하세요:" -ForegroundColor Yellow
    Write-Host "       git clone https://github.com/TTAJihoon/GSCert.git $RootDir" -ForegroundColor Yellow
    exit 1
}

# reference(PostgreSQL) 접속 정보 로드 (env.ps1 존재 시)
$EnvFile = Join-Path $RootDir "env.ps1"
if (Test-Path $EnvFile) { . $EnvFile }

# ── 다운로드 URL (버전 변경 시 여기만 수정) ─────────────────────────
$PYTHON_VER   = "3.13.3"
$PYTHON_URL   = "https://www.python.org/ftp/python/$PYTHON_VER/python-$PYTHON_VER-amd64.exe"
$GIT_VER      = "2.54.0"
$GIT_URL      = "https://github.com/git-for-windows/git/releases/download/v$GIT_VER.windows.1/Git-$GIT_VER-64-bit.exe"
$VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
$NGINX_VER    = "1.29.8"
$NGINX_URL    = "https://nginx.org/download/nginx-$NGINX_VER.zip"
$LIBREOFFICE_VER = "25.8.7"
$LIBREOFFICE_URL = "https://download.documentfoundation.org/libreoffice/stable/$LIBREOFFICE_VER/win/x86_64/LibreOffice_${LIBREOFFICE_VER}_Win_x86-64.msi"

# ── 헬퍼 ──────────────────────────────────────────────────────────────
function Step($msg)  { Write-Host "`n[....] $msg" -ForegroundColor Cyan }
function OK($msg)    { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[ -- ] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

function Refresh-Path {
    $m = [System.Environment]::GetEnvironmentVariable("Path","Machine")
    $u = [System.Environment]::GetEnvironmentVariable("Path","User")
    $env:Path = "$m;$u"
}

function Get-ServerIP {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' } |
           Sort-Object PrefixLength -Descending | Select-Object -First 1).IPAddress
    if (-not $ip) { $ip = "localhost" }
    return $ip
}

# 로컬 파일 우선 → 없으면 다운로드
function Get-OrDownload($name, $url, $destPath) {
    if (Test-Path $destPath) {
        Warn "$name 로컬 파일 사용: $(Split-Path $destPath -Leaf)"
        return
    }
    Write-Host "       다운로드 중: $name"
    Write-Host "       URL: $url"
    $prev = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
    try {
        Invoke-WebRequest -Uri $url -OutFile $destPath -UseBasicParsing
    } catch {
        $ProgressPreference = $prev
        Fail "$name 다운로드 실패: $_`n`n       수동 해결: $url 에서 파일을 받아 $destPath 에 저장 후 다시 실행하세요."
    }
    $ProgressPreference = $prev
    $sizeMB = [math]::Round((Get-Item $destPath).Length/1MB, 1)
    OK "$name 다운로드 완료 (${sizeMB} MB)"
}

# ── 배너 ──────────────────────────────────────────────────────────────
Clear-Host
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   GSCert 초기 환경 설정" -ForegroundColor Yellow
Write-Host "   프로젝트 경로: $RootDir" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan

# ══════════════════════════════════════════════════════════════════════
# 0. env.ps1 생성 마법사 (없을 때만)
# ══════════════════════════════════════════════════════════════════════
if (-not (Test-Path $EnvFile)) {
    Step "PostgreSQL 접속 설정 (env.ps1 생성)"
    Write-Host "  이 서버의 역할을 선택하세요:" -ForegroundColor Yellow
    Write-Host "    1) 주 서버  — PostgreSQL이 이 PC에 설치되어 있음 (HOST=localhost)"
    Write-Host "    2) 서브 서버 — 다른 서버의 PostgreSQL에 원격 접속"
    $role = Read-Host "  선택 (1/2)"
    if ($role -eq '2') {
        $pgHost = Read-Host "  PostgreSQL 서버 IP 입력"
        if (-not $pgHost) { $pgHost = "localhost" }
    } else {
        $pgHost = "localhost"
    }
    $pgPassword = Read-Host "  PostgreSQL 비밀번호 입력"

    $envLines = @(
        "# PostgreSQL reference DB 접속 정보",
        "`$env:REFERENCE_PG_NAME     = `"gscert_reference`"",
        "`$env:REFERENCE_PG_USER     = `"postgres`"",
        "`$env:REFERENCE_PG_PASSWORD = `"$pgPassword`"",
        "`$env:REFERENCE_PG_HOST     = `"$pgHost`"",
        "`$env:REFERENCE_PG_PORT     = `"5432`""
    )
    [System.IO.File]::WriteAllLines($EnvFile, $envLines, [System.Text.Encoding]::UTF8)
    . $EnvFile
    OK "env.ps1 생성 완료 (HOST: $pgHost)"
}

# ══════════════════════════════════════════════════════════════════════
# 1. VC++ Redistributable
# ══════════════════════════════════════════════════════════════════════
Step "VC++ Redistributable 설치 확인"
$vcInstalled = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" -ErrorAction SilentlyContinue
if ($vcInstalled) {
    Warn "VC++ Redistributable 이미 설치되어 있습니다."
} else {
    $vcFile = Join-Path $SetupDir "vc_redist.x64.exe"
    Get-OrDownload "VC++ Redistributable" $VCREDIST_URL $vcFile
    Write-Host "       설치 중..."
    Start-Process -FilePath $vcFile -ArgumentList "/install /quiet /norestart" -Wait
    OK "VC++ Redistributable 설치 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 2. Python
# ══════════════════════════════════════════════════════════════════════
Step "Python $PYTHON_VER 설치 확인"
Refresh-Path
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $ver = & python --version 2>&1
    OK "$ver 확인됨 ($($pythonCmd.Source))"
} else {
    $pyFile = Join-Path $SetupDir "python-$PYTHON_VER-amd64.exe"
    Get-OrDownload "Python $PYTHON_VER" $PYTHON_URL $pyFile
    Write-Host "       설치 중 (시간이 걸릴 수 있습니다)..."
    Start-Process -FilePath $pyFile -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    Refresh-Path
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) { Fail "Python 설치 후에도 찾을 수 없습니다. 재부팅 후 다시 시도하세요." }
    OK "Python 설치 완료 ($($pythonCmd.Source))"
}

# ══════════════════════════════════════════════════════════════════════
# 3. Git
# ══════════════════════════════════════════════════════════════════════
Step "Git $GIT_VER 설치 확인"
Refresh-Path
$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($gitCmd) {
    $ver = & git --version 2>&1
    OK "$ver 확인됨"
} else {
    $gitFile = Join-Path $SetupDir "Git-$GIT_VER-64-bit.exe"
    Get-OrDownload "Git $GIT_VER" $GIT_URL $gitFile
    Write-Host "       설치 중..."
    Start-Process -FilePath $gitFile `
        -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /COMPONENTS=`"icons,ext\reg\shellhere,assoc,assoc_sh`"" `
        -Wait
    Refresh-Path
    OK "Git 설치 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 4. nginx 설치 및 설정
# ══════════════════════════════════════════════════════════════════════
Step "nginx $NGINX_VER 설치 및 설정"
$NginxInstallDir = "C:\nginx-$NGINX_VER"
$NginxExe        = Join-Path $NginxInstallDir "nginx.exe"
$NginxConf       = Join-Path $NginxInstallDir "conf\nginx.conf"
$NginxTemplate   = Join-Path $SetupDir "nginx.conf"

if (-not (Test-Path $NginxExe)) {
    $nginxZip = Join-Path $SetupDir "nginx-$NGINX_VER.zip"
    Get-OrDownload "nginx $NGINX_VER" $NGINX_URL $nginxZip
    Write-Host "       압축 해제 중: C:\"
    Expand-Archive -Path $nginxZip -DestinationPath "C:\" -Force
    OK "nginx 압축 해제 완료"
} else {
    Warn "nginx 이미 설치되어 있습니다: $NginxInstallDir"
}

# conf 업데이트 (템플릿 → 실제 경로/IP 치환)
if (-not (Test-Path $NginxTemplate)) {
    Fail "nginx.conf 템플릿이 없습니다: $NginxTemplate"
}
$serverIP   = Get-ServerIP
$staticRoot = ($RootDir -replace '\\', '/') + '/staticfiles'
$conf = Get-Content $NginxTemplate -Raw -Encoding UTF8
$conf = $conf -replace '__SERVER_IP__',   $serverIP
$conf = $conf -replace '__STATIC_ROOT__', $staticRoot
[System.IO.File]::WriteAllText($NginxConf, $conf, [System.Text.Encoding]::ASCII)
OK "nginx.conf 설정 완료 (IP: $serverIP, static: $staticRoot)"

# 부팅 자동시작 스케줄러 등록
$taskName = "GSCert-nginx"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action    = New-ScheduledTaskAction -Execute $NginxExe -WorkingDirectory $NginxInstallDir
$trigger   = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
OK "nginx 부팅 자동시작 태스크 등록 완료"

# nginx 즉시 시작 또는 reload
$running = Get-Process -Name nginx -ErrorAction SilentlyContinue
if ($running) {
    & $NginxExe -s reload 2>$null
    OK "nginx conf reload 완료"
} else {
    Start-Process -FilePath $NginxExe -WorkingDirectory $NginxInstallDir -WindowStyle Hidden
    Start-Sleep -Seconds 1
    OK "nginx 시작 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 5. LibreOffice (.doc 등 구형 문서 변환용 — 다운로드 점검기에서 사용)
#    setup\ 폴더에 MSI가 있으면 그것을 사용하고, 없으면 다운로드한다(오프라인 설치 지원).
# ══════════════════════════════════════════════════════════════════════
Step "LibreOffice $LIBREOFFICE_VER 설치 확인 (.doc 문서 점검용)"
$LoExe = "C:\Program Files\LibreOffice\program\soffice.exe"
if (Test-Path $LoExe) {
    Warn "LibreOffice 이미 설치되어 있습니다: $LoExe"
} else {
    $loFile = Join-Path $SetupDir "LibreOffice_${LIBREOFFICE_VER}_Win_x86-64.msi"
    Get-OrDownload "LibreOffice $LIBREOFFICE_VER" $LIBREOFFICE_URL $loFile
    Write-Host "       설치 중 (수 분 소요될 수 있습니다)..."
    Start-Process -FilePath "msiexec.exe" -ArgumentList "/i `"$loFile`" /quiet /norestart" -Wait
    if (Test-Path $LoExe) {
        OK "LibreOffice 설치 완료"
    } else {
        Warn "LibreOffice 설치를 확인하지 못했습니다. 수동 설치가 필요할 수 있습니다."
    }
}

# ══════════════════════════════════════════════════════════════════════
# 6. Python 가상환경
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
& $VenvPython -m pip install --upgrade pip --quiet

# ══════════════════════════════════════════════════════════════════════
# 7. 기본 패키지 설치
# ══════════════════════════════════════════════════════════════════════
Step "기본 패키지 설치 (requirements.txt)"
& $VenvPip install -r (Join-Path $RootDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "기본 패키지 설치 실패" }
OK "기본 패키지 설치 완료"

# playwright는 playwright_job Django 앱이 최상위에서 import하므로 항상 설치
Step "playwright 설치 (Django 앱 구동 필수)"
& $VenvPip install "playwright>=1.59,<1.60" --quiet
if ($LASTEXITCODE -ne 0) { Fail "playwright 설치 실패" }
Write-Host "       Playwright Chromium 브라우저 설치 중..."
& $VenvPython -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Fail "Playwright Chromium 설치 실패" }
OK "playwright 설치 완료"

# ══════════════════════════════════════════════════════════════════════
# 8. Automation 패키지 (선택)
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
# 9. Search 패키지 (선택)
# ══════════════════════════════════════════════════════════════════════
if ($InstallSearch) {
    Step "Search 패키지 설치 (faiss, sentence-transformers 등)"
    & $VenvPip install -r (Join-Path $RootDir "requirements-search.txt")
    if ($LASTEXITCODE -ne 0) { Fail "Search 패키지 설치 실패" }
    OK "Search 패키지 설치 완료"
}

# ══════════════════════════════════════════════════════════════════════
# 10. 정적 파일 수집
# ══════════════════════════════════════════════════════════════════════
Step "정적 파일 수집 (collectstatic)"
& $VenvPython (Join-Path $RootDir "manage.py") collectstatic --noinput
if ($LASTEXITCODE -ne 0) { Fail "collectstatic 실패" }
OK "정적 파일 수집 완료"

# ══════════════════════════════════════════════════════════════════════
# 11. DB 마이그레이션
# ══════════════════════════════════════════════════════════════════════
Step "Django DB 마이그레이션"
& $VenvPython (Join-Path $RootDir "manage.py") migrate
if ($LASTEXITCODE -ne 0) { Fail "마이그레이션 실패 — 위 오류를 확인하세요." }
& $VenvPython (Join-Path $RootDir "manage.py") migrate --database=workflow
if ($LASTEXITCODE -ne 0) { Fail "workflow DB 마이그레이션 실패 — 위 오류를 확인하세요." }
OK "마이그레이션 완료"

# ══════════════════════════════════════════════════════════════════════
# 11-2. reference(PostgreSQL) DB — sw_data 테이블 마이그레이션 + 데이터 적재
#   PostgreSQL이 설치되어 있고 env.ps1(접속정보)이 준비된 경우에만 수행한다.
#   PG가 없거나 접속이 안 되면 실패시키지 않고 안내만 출력한다.
# ══════════════════════════════════════════════════════════════════════
Step "reference(PostgreSQL) DB 설정"
if (-not (Test-Path $EnvFile)) {
    Warn "env.ps1 이 없어 reference(PostgreSQL) DB 설정을 건너뜁니다."
    Write-Host "       1) PostgreSQL 설치 후 DB 생성:  CREATE DATABASE gscert_reference;" -ForegroundColor Gray
    Write-Host "       2) env.ps1.example 을 env.ps1 로 복사하고 비밀번호 입력" -ForegroundColor Gray
    Write-Host "       3) setup.ps1 을 다시 실행하거나 아래 두 명령을 수동 실행:" -ForegroundColor Gray
    Write-Host "          python manage.py migrate --database=reference" -ForegroundColor Gray
    Write-Host "          python manage.py import_reference_db --source-xlsx main/data/reference.xlsx" -ForegroundColor Gray
} else {
    # PostgreSQL 접속 확인 (psycopg)
    $pgOk = & $VenvPython -c "import os,psycopg; psycopg.connect(dbname=os.environ.get('REFERENCE_PG_NAME','gscert_reference'), user=os.environ.get('REFERENCE_PG_USER','postgres'), password=os.environ.get('REFERENCE_PG_PASSWORD',''), host=os.environ.get('REFERENCE_PG_HOST','localhost'), port=os.environ.get('REFERENCE_PG_PORT','5432')).close()" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Warn "PostgreSQL(gscert_reference)에 접속할 수 없어 reference DB 설정을 건너뜁니다."
        Write-Host "       오류: $pgOk" -ForegroundColor Gray
        Write-Host "       PostgreSQL 설치/실행 및 'CREATE DATABASE gscert_reference;' 후 env.ps1 의 비밀번호를 확인하세요." -ForegroundColor Gray
        Write-Host "       이후 수동 실행: python manage.py migrate --database=reference; python manage.py import_reference_db --source-xlsx main/data/reference.xlsx" -ForegroundColor Gray
    } else {
        & $VenvPython (Join-Path $RootDir "manage.py") migrate --database=reference
        if ($LASTEXITCODE -ne 0) { Fail "reference DB 마이그레이션 실패 — 위 오류를 확인하세요." }
        & $VenvPython (Join-Path $RootDir "manage.py") import_reference_db --source-xlsx (Join-Path $RootDir "main\data\reference.xlsx")
        if ($LASTEXITCODE -ne 0) { Fail "reference 데이터 적재 실패 — 위 오류를 확인하세요." }
        OK "reference(PostgreSQL) DB 설정 완료 (sw_data 마이그레이션 + reference.xlsx 적재)"
        if ($InstallSearch) {
            Write-Host "       FAISS 증분 임베딩 실행 중 (유사 시험 조회용, 수 분 소요)..." -ForegroundColor Gray
            & $VenvPython (Join-Path $RootDir "manage.py") embed_db
            if ($LASTEXITCODE -ne 0) { Warn "FAISS 임베딩 실패 — 나중에 launcher의 'I' 메뉴로 재시도하세요." }
            else { OK "FAISS 임베딩 완료" }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════
# 12. 바탕화면 단축아이콘 생성
# ══════════════════════════════════════════════════════════════════════
Step "바탕화면 단축아이콘 생성"
$WshShell     = New-Object -ComObject WScript.Shell
$ShortcutPath = "$([System.Environment]::GetFolderPath('Desktop'))\GSCert.lnk"
$Shortcut     = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath       = "powershell.exe"
$Shortcut.Arguments        = "-NoExit -ExecutionPolicy Bypass -File `"$RootDir\launcher.ps1`""
$Shortcut.WorkingDirectory = $RootDir
$Shortcut.WindowStyle      = 1
$Shortcut.IconLocation     = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe,0"
$Shortcut.Description      = "GSCert 서버 관리 메뉴"
$Shortcut.Save()
OK "단축아이콘 생성: $ShortcutPath"

# ══════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   환경 설정이 완료되었습니다." -ForegroundColor Green
Write-Host "   launcher에서 '1. start_all'로 서버를 시작하세요." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
