$ErrorActionPreference = "Stop"

$tesseract = Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe"
if (-not (Test-Path -LiteralPath $tesseract)) {
    winget install `
        --id UB-Mannheim.TesseractOCR `
        --exact `
        --silent `
        --accept-package-agreements `
        --accept-source-agreements `
        --disable-interactivity
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
