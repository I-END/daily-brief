# 一次性设置：把项目放到你的 GitHub、打开网站、存好密钥、跑第一次。
# 重复运行没关系，已经做过的步骤会跳过。
#   用法（在项目文件夹里）：powershell -ExecutionPolicy Bypass -File scripts\setup-github.ps1
$ErrorActionPreference = "Continue"   # native gh/git exit codes are checked by hand below
Set-Location (Split-Path $PSScriptRoot -Parent)
$repo = "daily-brief"

# 1. GitHub 登录
gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "先登录 GitHub（会打开浏览器）..." -ForegroundColor Yellow
    gh auth login --web --git-protocol https --scopes workflow
}
# 上传 .github/workflows 需要 workflow 权限；已登录但没有这个权限就补上
if (-not ((gh auth status 2>&1 | Out-String) -match "workflow")) {
    Write-Host "补充 workflow 权限（会打开浏览器）..." -ForegroundColor Yellow
    gh auth refresh -h github.com -s workflow
}
gh auth setup-git   # 让 git push 用 gh 的登录
$login = gh api user --jq .login
$uid = gh api user --jq .id
Write-Host "GitHub 账号：$login"

# 2. 本地 git 仓库和第一次提交
if (-not (Test-Path .git)) { git init -b main | Out-Null }
git config user.name $login
git config user.email "$uid+$login@users.noreply.github.com"
git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git commit -m "Daily brief: initial setup" | Out-Null }

# 3. 建公开仓库并推上去
gh repo view "$login/$repo" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh repo create $repo --public --source . --remote origin --push --description "每日简报 / Daily Brief"
} else {
    if (-not (git remote 2>$null | Select-String -Quiet origin)) { git remote add origin "https://github.com/$login/$repo.git" }
    git push -u origin main
}

# 4. 打开 GitHub Pages（用 Actions 部署）
gh api "repos/$login/$repo/pages" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { gh api -X POST "repos/$login/$repo/pages" -f build_type=workflow | Out-Null }
Write-Host "网站地址：https://$login.github.io/$repo/" -ForegroundColor Green

# 5. 密钥（粘贴时不会显示，粘完按回车；不想现在填就直接回车跳过）
$have = gh secret list -R "$login/$repo" | Out-String
foreach ($name in "DEEPSEEK_API_KEY", "FEISHU_WEBHOOK", "FEISHU_SECRET") {
    if ($have -match "(?m)^$name\s") { Write-Host "$name 已存在（要改就运行：gh secret set $name -R $login/$repo）"; continue }
    $v = Read-Host -AsSecureString "粘贴 $name（没有就直接回车）"
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($v))
    $plain = "$plain".Trim()
    if (-not $plain) { Write-Host "跳过 $name"; continue }
    gh secret set $name -R "$login/$repo" --body $plain
    if ($LASTEXITCODE -eq 0) { Write-Host "已保存 $name" -ForegroundColor Green } else { Write-Host "$name 保存失败" -ForegroundColor Red }
}
Write-Host "GitHub 上现在有这些密钥："
gh secret list -R "$login/$repo"

# 6. 立刻跑一次
gh workflow run daily.yml -R "$login/$repo" -f force=true
Write-Host "已经开始生成，大约 3 分钟。进度：https://github.com/$login/$repo/actions" -ForegroundColor Green
