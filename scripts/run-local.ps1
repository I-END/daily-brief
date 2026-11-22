# 在本机生成今天的日报（云端出问题时的备用方案）。密钥放在项目里的 .env 文件。
#   用法：powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1 [--force]
Set-Location (Split-Path $PSScriptRoot -Parent)
$venv = Join-Path $env:LOCALAPPDATA "daily-brief\venv"   # 放在 OneDrive 外面，免得同步一堆文件
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    py -3 -m venv $venv
    & $py -m pip install -q -r requirements.txt
}
& $py run.py @args
if (Test-Path site\index.html) { Start-Process (Resolve-Path site\index.html) }
