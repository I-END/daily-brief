# 只在你不用云端、想让本机每天自动跑时才用。云端和本地同时开会收到两份飞书推送。
# 每天早上 7:00 运行；那时电脑关着的话，下次开机后补跑。
#   安装：powershell -ExecutionPolicy Bypass -File scripts\install-local-task.ps1
#   卸载：Unregister-ScheduledTask -TaskName DailyBrief -Confirm:$false
$script = Join-Path $PSScriptRoot "run-local.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 7:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "DailyBrief" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "已设置：每天 7:00 生成日报（错过的话开机后补跑）"
