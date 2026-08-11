<#
.SYNOPSIS
  nginx.conf 템플릿을 실제 서버 IP/도메인/정적파일 경로로 치환해 nginx conf에 적용한다.
.PARAMETER Mode
  All              - 모든 페이지를 HTTPS로 서비스 (기본, setup/nginx.conf 템플릿)
  ConsultationOnly - /consultation/ 만 HTTPS, 나머지는 HTTP (setup/nginx-consultation-only-https.conf 템플릿)
#>
param(
    [ValidateSet('All', 'ConsultationOnly')]
    [string]$Mode = 'All'
)
$ErrorActionPreference = "Stop"
$RootDir  = "C:\Claude_GSCert"
$SetupDir = Join-Path $RootDir "setup"
$NginxInstallDir = "C:\nginx-1.29.8"
$NginxConf       = Join-Path $NginxInstallDir "conf\nginx.conf"

$TemplateName  = if ($Mode -eq 'ConsultationOnly') { "nginx-consultation-only-https.conf" } else { "nginx.conf" }
$NginxTemplate = Join-Path $SetupDir $TemplateName
if (-not (Test-Path $NginxTemplate)) {
    Write-Host "[ERROR] nginx.conf 템플릿이 없습니다: $NginxTemplate" -ForegroundColor Red
    exit 1
}

function Get-ServerIP {
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' } |
           Sort-Object PrefixLength -Descending | Select-Object -First 1).IPAddress
    if (-not $ip) { $ip = "localhost" }
    return $ip
}

$serverIP     = if ($env:MAIN_SERVER_IP) { $env:MAIN_SERVER_IP } else { Get-ServerIP }
# 구글 OAuth 등 도메인 필수 용도(IP 불가). SERVER_DOMAIN 환경변수(예: gsai.tta.or.kr)가 있으면
# 그 값을 쓰고, 없으면 공식 서비스 도메인을 사용한다.
$serverDomain = if ($env:SERVER_DOMAIN) { $env:SERVER_DOMAIN } else { "gsai.tta.or.kr" }
$staticRoot   = ($RootDir -replace '\\', '/') + '/staticfiles'

$conf = Get-Content $NginxTemplate -Raw -Encoding UTF8
$conf = $conf -replace '__SERVER_IP__',     $serverIP
$conf = $conf -replace '__SERVER_DOMAIN__', $serverDomain
$conf = $conf -replace '__STATIC_ROOT__',   $staticRoot
[System.IO.File]::WriteAllText($NginxConf, $conf, [System.Text.Encoding]::ASCII)

# 마지막으로 적용한 모드를 저장 (launcher 메뉴 표시 및 재시작 시 기본값으로 사용)
$RunDir = Join-Path $RootDir "run"
if (-not (Test-Path $RunDir)) { New-Item -ItemType Directory -Path $RunDir | Out-Null }
[System.IO.File]::WriteAllText((Join-Path $RunDir "nginx_mode.txt"), $Mode, [System.Text.Encoding]::ASCII)

Write-Host "[OK] nginx.conf 적용 완료 (모드: $Mode, IP: $serverIP, domain: $serverDomain)" -ForegroundColor Green
exit 0
