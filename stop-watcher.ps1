# stop-watcher.ps1 - 停止后台文件监控
# 用法：.\stop-watcher.ps1

Write-Host "停止文件监控..." -ForegroundColor Cyan

# 从PID文件读取进程ID
$pidFile = "$PSScriptRoot\.watcher.pid"
if (Test-Path $pidFile) {
    $processId = Get-Content $pidFile -Raw
    $processId = $processId.Trim()
    
    # 查找进程
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    
    if ($process) {
        Write-Host "找到监控进程（PID: $processId）" -ForegroundColor Yellow
        Stop-Process -Id $processId -Force
        Write-Host "文件监控已停止" -ForegroundColor Green
    } else {
        Write-Host "未找到运行中的监控进程（可能已停止）" -ForegroundColor Yellow
    }
    
    # 删除PID文件
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "未找到PID文件，尝试查找所有相关进程..." -ForegroundColor Yellow
    
    # 查找所有运行watch-and-sync.ps1的PowerShell进程
    $processes = Get-Process -Name "powershell" -ErrorAction SilentlyContinue | 
        Where-Object { $_.CommandLine -like "*watch-and-sync.ps1*" }
    
    if ($processes) {
        foreach ($proc in $processes) {
            Write-Host "停止进程 PID: $($proc.Id)" -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force
        }
        Write-Host "所有文件监控进程已停止" -ForegroundColor Green
    } else {
        Write-Host "未找到运行中的文件监控进程" -ForegroundColor Green
    }
}

# 清理事件订阅（如果当前会话中有）
Get-EventSubscriber | Unregister-Event -ErrorAction SilentlyContinue