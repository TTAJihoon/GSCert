# Claude 최신 버전 경로 자동 감지
$claudeInstall = Get-AppxPackage -Name "*Claude*" | Select-Object -ExpandProperty InstallLocation
$swiftShaderPath = "$claudeInstall\app\vk_swiftshader_icd.json"

if (Test-Path $swiftShaderPath) {
    [System.Environment]::SetEnvironmentVariable("VK_ICD_FILENAMES", $swiftShaderPath, "Machine")
    [System.Environment]::SetEnvironmentVariable("LIBGL_ALWAYS_SOFTWARE", "1", "Machine")
    [System.Environment]::SetEnvironmentVariable("GALLIUM_DRIVER", "softpipe", "Machine")
    Write-Host "SwiftShader 경로 설정 완료: $swiftShaderPath"
} else {
    Write-Host "경고: SwiftShader 파일을 찾을 수 없습니다: $swiftShaderPath"
}

# Local State GPU 비활성화
$localStatePath = "C:\Users\Administrator\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\Local State"
if (Test-Path $localStatePath) {
    Copy-Item $localStatePath "$localStatePath.bak" -Force
    $localState = Get-Content $localStatePath -Raw | ConvertFrom-Json
    if (-not $localState.gpu) {
        $localState | Add-Member -NotePropertyName "gpu" -NotePropertyValue ([PSCustomObject]@{ gpu_mode = 0 })
    } else {
        $localState.gpu.gpu_mode = 0
    }
    $localState | ConvertTo-Json -Depth 20 | Set-Content $localStatePath -Encoding UTF8
    Write-Host "Local State GPU 비활성화 완료"
}

# GPU 캐시 삭제
$base = "C:\Users\Administrator\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude"
Remove-Item "$base\GPUCache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$base\DawnWebGPUCache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$base\DawnGraphiteCache" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "GPU 캐시 삭제 완료"

Write-Host ""
Write-Host "모든 설정 완료. Claude Desktop을 재시작하세요."
