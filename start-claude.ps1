# Claude Desktop 종료
Get-Process -Name "claude" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# GPU 비활성화 플래그로 실행
Start-Process "C:\Program Files\WindowsApps\Claude_1.14271.0.0_x64__pzs8sxrjxfjjc\app\claude.exe" `
    -ArgumentList "--disable-gpu","--disable-gpu-compositing","--disable-software-rasterizer","--disable-gpu-sandbox","--no-sandbox"
