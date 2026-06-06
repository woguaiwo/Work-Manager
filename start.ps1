[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "    Work Manager - 工作管理系统" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "正在启动..." -ForegroundColor Green
Write-Host ""
try {
    python main.py
} catch {
    Write-Host "[错误] 启动失败，请确保已安装 Python 和依赖包" -ForegroundColor Red
    Write-Host "运行: pip install PyQt6 matplotlib pywin32 psutil" -ForegroundColor Yellow
    pause
}
