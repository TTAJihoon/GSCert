<#
.SYNOPSIS
  Cloudflare Tunnel(cloudflared) 설치 — 새 서버로 이전할 때도 바로 재설치 가능하도록 구성한다.
.DESCRIPTION
  setup.ps1 의 Get-OrDownload 관례를 그대로 따른다: setup\ 폴더에 실행파일이 이미 있으면
  다운로드를 건너뛰고 로컬 파일을 쓴다(오프라인 설치 지원). 최초 다운로드 후에는 setup\ 에도
  캐시해두므로, 다음 서버에서는 이 스크립트 + setup\ 폴더만 그대로 복사하면 재다운로드가
  필요 없다.

  최초 설치(이 서버에 Tunnel 자격증명이 아직 없을 때):
    이 스크립트는 바이너리만 설치하고 끝난다. 아래를 1회 수동으로 진행해야 한다.
      1) cloudflared tunnel login                              (브라우저 인증 — 본인이 직접)
      2) cloudflared tunnel create gscert-<서버명>
      3) setup\cloudflared-config.yml 을 참고해 %USERPROFILE%\.cloudflared\config.yml 작성
      4) (DNS 위임 완료 후) cloudflared tunnel route dns gscert-<서버명> gsai.tta.or.kr
      5) 이 스크립트를 다시 실행 — cert.pem/config.yml 이 이미 있으므로 자동으로 서비스 등록까지 됨.

  서버 이전 시(자격증명을 그대로 이관): 기존 서버의 %USERPROFILE%\.cloudflared\ 폴더 전체
  (cert.pem, <tunnel-id>.json, config.yml)를 새 서버의 같은 경로에 복사한 뒤 이 스크립트를
  실행하면, 로그인/터널 재생성 없이 바로 서비스로 등록·시작된다. Tunnel 은 서버가 아니라
  자격증명 파일에 묶여 있으므로 이 방식이 공식적으로 지원된다.
#>
$ErrorActionPreference = "Stop"
$RootDir  = "C:\Claude_GSCert"
$SetupDir = Join-Path $RootDir "setup"

$CLOUDFLARED_VER = "2026.7.3"
$CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/download/$CLOUDFLARED_VER/cloudflared-windows-amd64.exe"
$InstallDir = "C:\cloudflared"
$ExePath    = Join-Path $InstallDir "cloudflared.exe"
$LocalCache = Join-Path $SetupDir "cloudflared-windows-amd64.exe"

function Step($msg)  { Write-Host "`n[....] $msg" -ForegroundColor Cyan }
function OK($msg)    { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[ -- ] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[FAIL] $msg" -ForegroundColor Red; exit 1 }

# ══════════════════════════════════════════════════════════════════════
# 1. cloudflared 바이너리 설치 (로컬 캐시 우선 → 없으면 다운로드)
# ══════════════════════════════════════════════════════════════════════
Step "cloudflared $CLOUDFLARED_VER 설치 확인"
if (-not (Test-Path $InstallDir)) { New-Item -ItemType Directory -Path $InstallDir | Out-Null }

if (Test-Path $ExePath) {
    Warn "cloudflared 이미 설치되어 있습니다: $ExePath"
} else {
    if (Test-Path $LocalCache) {
        Warn "cloudflared 로컬 캐시 사용: $LocalCache"
        Copy-Item $LocalCache $ExePath -Force
    } else {
        Write-Host "       다운로드 중: cloudflared $CLOUDFLARED_VER"
        Write-Host "       URL: $CLOUDFLARED_URL"
        $prev = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
        try {
            Invoke-WebRequest -Uri $CLOUDFLARED_URL -OutFile $ExePath -UseBasicParsing
        } catch {
            $ProgressPreference = $prev
            Fail "cloudflared 다운로드 실패: $_`n       수동 해결: $CLOUDFLARED_URL 에서 받아 $ExePath 에 저장 후 다시 실행하세요."
        }
        $ProgressPreference = $prev
        $sizeMB = [math]::Round((Get-Item $ExePath).Length/1MB, 1)
        OK "cloudflared 다운로드 완료 (${sizeMB} MB)"
        # 다음 서버 이전 시 재다운로드 없이 쓸 수 있도록 setup\ 에도 캐시해둔다.
        Copy-Item $ExePath $LocalCache -Force
    }
    OK "cloudflared 설치 완료: $ExePath"
}

$verOutput = & $ExePath --version 2>&1
OK "버전 확인: $verOutput"

# ══════════════════════════════════════════════════════════════════════
# 2. 자격증명 확인 — 있으면(이관/재설치) 서비스로 바로 등록, 없으면(최초) 안내만 출력
# ══════════════════════════════════════════════════════════════════════
Step "Tunnel 자격증명 확인"
$credDir   = Join-Path $env:USERPROFILE ".cloudflared"
$hasCert   = Test-Path (Join-Path $credDir "cert.pem")
$hasConfig = Test-Path (Join-Path $credDir "config.yml")

if ($hasCert -and $hasConfig) {
    OK "기존 인증서/config.yml 발견: $credDir (이관된 것으로 판단)"
    Step "Windows 서비스로 등록"
    & $ExePath service install
    if ($LASTEXITCODE -ne 0) { Fail "cloudflared 서비스 등록 실패 — 위 오류를 확인하세요." }
    Start-Sleep -Seconds 1
    try {
        Start-Service -Name "Cloudflared" -ErrorAction Stop
        OK "cloudflared 서비스 등록 및 시작 완료"
    } catch {
        Warn "서비스 등록은 됐지만 시작 확인 실패 — services.msc 에서 'Cloudflared' 상태를 확인하세요: $_"
    }
} else {
    Warn "자격증명이 없습니다 (최초 설치) — 아래를 1회 수동으로 진행하세요:"
    Write-Host "  1) $ExePath tunnel login" -ForegroundColor Gray
    Write-Host "  2) $ExePath tunnel create gscert-194" -ForegroundColor Gray
    Write-Host "  3) setup\cloudflared-config.yml 참고해 $credDir\config.yml 작성" -ForegroundColor Gray
    Write-Host "  4) (DNS 위임 완료 후) $ExePath tunnel route dns gscert-194 gsai.tta.or.kr" -ForegroundColor Gray
    Write-Host "  5) 이 스크립트 재실행 -> 서비스 자동 등록" -ForegroundColor Gray
}
