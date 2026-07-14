# watch-and-sync.ps1 - 文件监控自动同步脚本
# 监控目录变化，自动提交并推送到GitHub
# 用法：.\watch-and-sync.ps1
# 按 Ctrl+C 停止监控

param(
    [int]$DebounceSeconds = 5  # 防抖动时间（秒）
)

Write-Host "启动文件监控..." -ForegroundColor Cyan
Write-Host "监控目录：$(Get-Location)" -ForegroundColor Yellow
Write-Host "防抖动时间：$DebounceSeconds 秒" -ForegroundColor Yellow
Write-Host "按 Ctrl+C 停止监控" -ForegroundColor Red
Write-Host ""

# 检查是否在Git仓库中
if (-not (Test-Path ".git")) {
    Write-Host "错误：当前目录不是Git仓库" -ForegroundColor Red
    exit 1
}

# 创建文件系统监控器
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = Get-Location
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

# 忽略的目录和文件模式（与.gitignore保持一致）
$ignorePatterns = @(
    '\.git\\',
    '__pycache__\\',
    '\.codebuddy\\',
    '\.venv\\',
    '\\.*\.pyc$',
    '\\.*\.pyo$',
    '\\.*\.pyd$',
    '\\.*\.png$',
    '\\.*\.jpg$',
    '\\.*\.jpeg$',
    '\\.*\.gif$',
    '\\.*\.webp$',
    '\\.*\.bmp$',
    '\\.*\.mp4$',
    '\\.*\.wav$',
    '\\.*\.mp3$',
    'backup_before_preset_',
    '\\-p\\'
)

# 检查文件是否应该被忽略
function ShouldIgnoreFile($filePath) {
    $relativePath = $filePath.Replace((Get-Location).Path, '').TrimStart('\')
    foreach ($pattern in $ignorePatterns) {
        if ($relativePath -match $pattern) {
            return $true
        }
    }
    return $false
}

# 同步函数
function SyncToGitHub {
    Write-Host "`n检测到文件变化，准备同步..." -ForegroundColor Cyan
    
    # 检查是否有实际更改
    $status = git status --porcelain
    if ([string]::IsNullOrEmpty($status)) {
        Write-Host "没有实质性更改，跳过同步" -ForegroundColor Yellow
        return
    }
    
    # 生成提交信息
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $changedFiles = ($status | Measure-Object).Count
    $commitMessage = "自动同步: $timestamp ($changedFiles 个文件)"
    
    # 添加、提交、推送
    Write-Host "添加更改..." -ForegroundColor Yellow
    git add .
    
    Write-Host "提交更改: $commitMessage" -ForegroundColor Yellow
    git commit -m $commitMessage
    
    Write-Host "推送到GitHub..." -ForegroundColor Yellow
    git push
    
    Write-Host "同步完成！" -ForegroundColor Green
}

# 防抖动计时器
$lastSyncTime = [DateTime]::MinValue
$syncTimer = $null

# 文件变化事件处理
$action = {
    $path = $Event.SourceEventArgs.FullPath
    $changeType = $Event.SourceEventArgs.ChangeType
    
    # 忽略特定文件
    if (ShouldIgnoreFile $path) {
        return
    }
    
    Write-Host "`n检测到变化: $changeType - $path" -ForegroundColor Gray
    
    # 防抖动处理
    $now = Get-Date
    if (($now - $lastSyncTime).TotalSeconds -lt $DebounceSeconds) {
        Write-Host "防抖动：等待更多变化..." -ForegroundColor DarkGray
        if ($syncTimer) {
            $syncTimer.Stop()
        }
    }
    
    $lastSyncTime = $now
    $syncTimer = New-Object System.Timers.Timer
    $syncTimer.Interval = $DebounceSeconds * 1000
    $syncTimer.AutoReset = $false
    $syncTimer.Add_Elapsed({
        SyncToGitHub
        $syncTimer.Dispose()
    })
    $syncTimer.Start()
}

# 注册事件
Register-ObjectEvent $watcher "Created" -Action $action
Register-ObjectEvent $watcher "Changed" -Action $action
Register-ObjectEvent $watcher "Deleted" -Action $action
Register-ObjectEvent $watcher "Renamed" -Action $action

Write-Host "文件监控已启动，等待变化..." -ForegroundColor Green

# 保持脚本运行
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    # 清理
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Get-EventSubscriber | Unregister-Event
    Write-Host "`n文件监控已停止" -ForegroundColor Red
}