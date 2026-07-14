# sync.ps1 - 手动同步脚本
# 用法：.\sync.ps1 [提交信息]
# 示例：.\sync.ps1 "修复了LoRA加载器的BUG"

param(
    [string]$commitMessage = "自动同步: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
)

Write-Host "开始同步代码到GitHub..." -ForegroundColor Cyan

# 检查是否在Git仓库中
if (-not (Test-Path ".git")) {
    Write-Host "错误：当前目录不是Git仓库" -ForegroundColor Red
    exit 1
}

# 添加所有更改（尊重.gitignore规则）
Write-Host "添加更改..." -ForegroundColor Yellow
git add .

# 检查是否有更改需要提交
$status = git status --porcelain
if ([string]::IsNullOrEmpty($status)) {
    Write-Host "没有检测到更改，无需提交" -ForegroundColor Green
    exit 0
}

# 显示将要提交的文件
Write-Host "检测到以下更改：" -ForegroundColor Yellow
$status | ForEach-Object { Write-Host "  $_" }

# 提交更改
Write-Host "提交更改..." -ForegroundColor Yellow
git commit -m $commitMessage

# 推送到GitHub
Write-Host "推送到GitHub..." -ForegroundColor Yellow
git push

Write-Host "同步完成！" -ForegroundColor Green