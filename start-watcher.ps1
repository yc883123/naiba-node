# start-watcher.ps1 - 启动后台文件监控
# 用法：.\start-watcher.ps1

Write-Host "启动后台文件监控..." -ForegroundColor Cyan

# 检查是否已有监控进程在运行
$processName = "powershell"
$processArgs = "-File `"$PSScriptRoot\watch-and-sync.ps1`""
$existingProcess = Get-Process -Name $processName -ErrorAction SilentlyContinue | 
    Where-Object { $_.CommandLine -like "*watch-and-sync.ps1*" }

if ($existingProcess) {
    Write-Host "文件监控已在运行（PID: $($existingProcess.Id)）" -ForegroundColor Yellow
    Write-Host "如需重启，请先运行 .\stop-watcher.ps1" -ForegroundColor Yellow
    exit 0
}

# 启动后台进程
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = "powershell.exe"
$startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\watch-and-sync.ps1`""
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true

$process = [System.Diagnostics.Process]::Start($startInfo)

# 等待启动
Start-Sleep -Seconds 2

if (!$process.HasExited) {
    Write-Host "文件监控已启动（PID: $($process.Id)）" -ForegroundColor Green
    Write-Host "监控将在后台持续运行" -ForegroundColor Green
    Write-Host "使用 .\stop-watcher.ps1 停止监控" -ForegroundColor Yellow
    Write-Host "使用 .\sync.ps1 手动同步" -ForegroundColor Yellow
    
    # 保存PID到文件
    $process.Id | Out-File -FilePath "$PSScriptRoot\.watcher.pid" -Encoding ASCII
} else {
    Write-Host "启动文件监控失败" -ForegroundColor Red
    Write-Host "错误信息：" -ForegroundColor Red
    $process.StandardError.ReadToEnd()
}