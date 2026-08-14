<#
.SYNOPSIS
  nginx HTTPS 용 자체서명 인증서(gscert.crt/gscert.key)를 nginx conf 폴더에 생성한다.
  http 로 받은 다운로드에 붙는 브라우저 경고("보안 연결 아님")를 없애기 위한 https 전환용.

.PARAMETER ServerIp
  인증서 SAN(및 CN)에 넣을 서버 IP. 브라우저에서 접속하는 주소와 반드시 일치해야 한다.

.PARAMETER NginxConfDir
  인증서를 저장할 nginx conf 폴더. nginx.conf 의 ssl_certificate 상대경로 기준.

.NOTES
  - openssl 이 PATH 에 없으면 Git 동봉 openssl(C:\Program Files\Git\usr\bin\openssl.exe)을 자동 사용한다.
  - 생성 후 각 클라이언트 PC 의 "신뢰할 수 있는 루트 인증 기관"에 gscert.crt 를 등록하면
    자체서명 경고까지 사라진다(certlm.msc 또는 GPO 배포).
#>
param(
    [string]$ServerIp = "210.96.71.194",
    [string]$ServerDomain = "gsai.tta.or.kr",   # 운영 HTTPS/OAuth에 사용하는 정식 도메인.
    [string]$NginxConfDir = "C:\nginx-1.29.8\conf"
)
$ErrorActionPreference = "Stop"

$openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $openssl) {
    $candidates = @(
        "C:\Program Files\Git\usr\bin\openssl.exe",
        "C:\Program Files\Git\mingw64\bin\openssl.exe",
        "C:\Program Files (x86)\Git\usr\bin\openssl.exe"
    )
    $openssl = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $openssl) {
    Write-Host "[ERROR] openssl 을 찾을 수 없습니다. Git 설치 또는 openssl PATH 등록이 필요합니다." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $NginxConfDir)) {
    Write-Host "[ERROR] nginx conf 폴더가 없습니다: $NginxConfDir" -ForegroundColor Red
    exit 1
}

$crt = Join-Path $NginxConfDir "gscert.crt"
$key = Join-Path $NginxConfDir "gscert.key"

# CN 은 도메인, SAN 에는 IP 와 도메인을 모두 넣어 두 주소 접속 모두 무경고 처리.
# (기존 https://<IP>/ 접속 유지 + https://<도메인>/ 신규 접속 지원)
$san = "subjectAltName=IP:$ServerIp,DNS:$ServerDomain"
& $openssl req -x509 -nodes -newkey rsa:2048 `
    -keyout $key -out $crt -days 3650 `
    -subj "/CN=$ServerDomain" `
    -addext $san

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] 인증서 생성 실패" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] 인증서 생성 완료:" -ForegroundColor Green
Write-Host "     $crt"
Write-Host "     $key"
Write-Host "다음: nginx.conf 에 443 ssl 블록이 있는지 확인 후  nginx.exe -t  &&  nginx.exe -s reload"
Write-Host "경고 완전 제거: 각 클라이언트의 '신뢰할 수 있는 루트 인증 기관'에 gscert.crt 등록"
