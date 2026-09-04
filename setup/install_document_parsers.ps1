$ErrorActionPreference = "Stop"

$tesseract = Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe"
if (-not (Test-Path -LiteralPath $tesseract)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install `
            --id UB-Mannheim.TesseractOCR `
            --exact `
            --silent `
            --accept-package-agreements `
            --accept-source-agreements `
            --disable-interactivity
    }
    else {
        # Windows Server SKUs ship without App Installer, so winget is unavailable.
        # Fall back to the same UB-Mannheim build the winget package points at.
        $installerUrl = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
        $installer = Join-Path $env:TEMP "tesseract-ocr-w64-setup-5.4.0.20240606.exe"
        Write-Host "winget을 찾지 못해 UB-Mannheim 설치 파일을 직접 내려받습니다."
        $previousProgress = $ProgressPreference
        $ProgressPreference = "SilentlyContinue"
        try {
            Invoke-WebRequest -Uri $installerUrl -OutFile $installer -UseBasicParsing
        }
        finally {
            $ProgressPreference = $previousProgress
        }
        $process = Start-Process -FilePath $installer -ArgumentList "/S" -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Tesseract 설치에 실패했습니다. 종료 코드: $($process.ExitCode)"
        }
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath $tesseract)) {
    throw "Tesseract 설치를 확인하지 못했습니다: $tesseract"
}

$tessdata = Join-Path $env:LOCALAPPDATA "GSCert\tessdata"
New-Item -ItemType Directory -Force -Path $tessdata | Out-Null

$installedTessdata = Join-Path $env:ProgramFiles "Tesseract-OCR\tessdata"
foreach ($language in @("eng", "osd")) {
    $source = Join-Path $installedTessdata "$language.traineddata"
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination $tessdata -Force
    }
}

$koreanData = Join-Path $tessdata "kor.traineddata"
Invoke-WebRequest `
    -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/refs/heads/main/kor.traineddata" `
    -OutFile $koreanData

& $tesseract --tessdata-dir $tessdata --list-langs
