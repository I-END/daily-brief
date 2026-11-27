# 换 DeepSeek key：先验证，有效才存进 GitHub（粘贴时屏幕上不显示）。
#   用法（在项目文件夹里）：powershell -ExecutionPolicy Bypass -File scripts\set-deepseek-key.ps1
$ErrorActionPreference = "Continue"
$repo = (gh repo view --json nameWithOwner --jq .nameWithOwner 2>$null)
if (-not $repo) { $repo = "$(gh api user --jq .login)/daily-brief" }
$s = Read-Host -AsSecureString "粘贴新的 DeepSeek key"
$k = ([Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))).Trim()
if (-not $k) { Write-Host "没有输入，什么都没改"; exit 1 }
try {
    $r = Invoke-RestMethod https://api.deepseek.com/models -Headers @{ Authorization = "Bearer $k" }
} catch {
    Write-Host "这个 key 无效，没有保存：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
gh secret set DEEPSEEK_API_KEY -R $repo --body $k
if ($LASTEXITCODE -ne 0) { Write-Host "key 有效，但存进 GitHub 失败" -ForegroundColor Red; exit 1 }
Write-Host ("key 有效，已保存到 $repo。可用模型：" + ($r.data.id -join ", ")) -ForegroundColor Green
gh workflow run daily.yml -R $repo -f force=true
if ($LASTEXITCODE -eq 0) { Write-Host "已开始重新生成今天的日报，大约 3-5 分钟后看网站和飞书。" -ForegroundColor Green }
