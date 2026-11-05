# Windows Task Scheduler Automation for Indian Stock Market Day Trading Suite
# Configures automated market-hours triggers for 09:08 AM (Pre-Open), 09:35 AM (ORB Scan), and 15:10 PM (Flat-By Squareoff)

$TradingRoot = "C:\Users\shant\Downloads\CLAUDE\trading"
$PythonExe = (Get-Command python).Source

Write-Host "Configuring Indian Market Automated Triggers in $TradingRoot..." -ForegroundColor Cyan

# 1. 09:08 AM IST - Morning Pre-Open & News Check
$ActionPreOpen = New-ScheduledTaskAction -Execute $PythonExe -Argument "$TradingRoot\skills\trader-scanner\preopen.py" -WorkingDirectory $TradingRoot
$TriggerPreOpen = New-ScheduledTaskTrigger -Daily -At "09:08AM"
Register-ScheduledTask -TaskName "NSE_Trading_PreOpen_0908" -Action $ActionPreOpen -Trigger $TriggerPreOpen -Description "NSE Pre-Open Scan" -Force | Out-Null
Write-Host "  [OK] Registered NSE_Trading_PreOpen_0908 (09:08 AM Daily)" -ForegroundColor Green

# 2. 09:35 AM IST - 15-Minute Opening Range Breakout Scan
$ActionORB = New-ScheduledTaskAction -Execute $PythonExe -Argument "$TradingRoot\skills\trader-scanner\scan.py orb" -WorkingDirectory $TradingRoot
$TriggerORB = New-ScheduledTaskTrigger -Daily -At "09:35AM"
Register-ScheduledTask -TaskName "NSE_Trading_ORB_0935" -Action $ActionORB -Trigger $TriggerORB -Description "NSE 15m ORB Breakout Scan" -Force | Out-Null
Write-Host "  [OK] Registered NSE_Trading_ORB_0935 (09:35 AM Daily)" -ForegroundColor Green

# 3. 15:10 PM IST - Mandatory Broker Auto-Squareoff Warning
$ActionFlatBy = New-ScheduledTaskAction -Execute $PythonExe -Argument "$TradingRoot\skills\trader-alerts\alerts.py check" -WorkingDirectory $TradingRoot
$TriggerFlatBy = New-ScheduledTaskTrigger -Daily -At "03:10PM"
Register-ScheduledTask -TaskName "NSE_Trading_FlatBy_1510" -Action $ActionFlatBy -Trigger $TriggerFlatBy -Description "NSE MIS Auto-Squareoff Reminder" -Force | Out-Null
Write-Host "  [OK] Registered NSE_Trading_FlatBy_1510 (03:10 PM Daily)" -ForegroundColor Green

Write-Host "`nAll 3 market-hours automated triggers configured successfully." -ForegroundColor Cyan

