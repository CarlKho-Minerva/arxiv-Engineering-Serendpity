<#
Install / update / remove the Overwatch session logger on the gaming PC.

  powershell -ExecutionPolicy Bypass -File install.ps1              # install or update, start, verify
  powershell -ExecutionPolicy Bypass -File install.ps1 -SelfTest    # also run the Notepad end-to-end test
  powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall   # stop and remove the task (keeps data)

Run it from the directory that holds logger.py (it copies logger.py and selftest.py to
%LOCALAPPDATA%\ow_logger). Needs Carl to be logged on to the desktop: the task runs in
his interactive session because Desktop Duplication and Raw Input need it.

Supervision (tested on this PC, see memory windows-task-supervision): a TimeTrigger whose
StartBoundary is in the past, repeating every minute with no duration, plus
MultipleInstancesPolicy=IgnoreNew. While the logger lives every repeat is ignored; within
60 s of it dying the next repeat restarts it. RestartOnFailure and a LogonTrigger with
repetition do NOT work here (Next Run Time shows N/A).
#>
param(
    [switch]$Uninstall,
    [switch]$SelfTest,
    [string]$Target = 'Overwatch.exe',
    [string]$OutDir = 'D:\ow_capture'
)
$ErrorActionPreference = 'Stop'
$TaskName = 'OWCaptureLogger'
$AppDir = Join-Path $env:LOCALAPPDATA 'ow_logger'
$Py = 'C:\Program Files\Python312\pythonw.exe'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $TaskName
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        "removed $TaskName (recordings in $OutDir are kept)"
    } else { "$TaskName not installed" }
    exit 0
}

if (-not (Test-Path $Py)) { throw "pythonw not found at $Py" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw 'ffmpeg not on PATH' }
New-Item -ItemType Directory -Force $AppDir, $OutDir | Out-Null
foreach ($f in 'logger.py', 'selftest.py') { Copy-Item (Join-Path $PSScriptRoot $f) $AppDir -Force }

if ($SelfTest) {
    $name = 'OWLogger-SelfTest'
    $a = New-ScheduledTaskAction -Execute $Py -Argument "`"$AppDir\selftest.py`" `"$OutDir\_selftest`" 30"
    $t = New-ScheduledTaskTrigger -Once -At ([datetime]'2021-01-01T00:00:00')
    $p = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName $name -Action $a -Trigger $t -Principal $p -Force | Out-Null
    Remove-Item "$OutDir\_selftest\selftest_result.json" -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $name
    $deadline = (Get-Date).AddMinutes(5)
    while (-not (Test-Path "$OutDir\_selftest\selftest_result.json")) {
        if ((Get-Date) -gt $deadline) { throw 'self-test did not finish within 5 minutes' }
        Start-Sleep 3
    }
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Get-Content "$OutDir\_selftest\selftest_result.json"
    $r = Get-Content "$OutDir\_selftest\selftest_result.json" | ConvertFrom-Json
    if (-not $r.ok) { throw 'self-test FAILED (see above and _selftest\logger.log)' }
}

# End the running instance first: /create /f alone leaves the old process running old code.
# Stop-ScheduledTask returns before the process is gone; a new instance started in that window
# sees the old one's mutex and exits 3, so wait for (or kill) every old logger process.
function Get-LoggerProcs {
    @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and
        $_.CommandLine -like "*ow_logger\logger.py*--out `"$OutDir`"*" })
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $TaskName }
$deadline = (Get-Date).AddSeconds(15)
while (@(Get-LoggerProcs).Count -gt 0 -and (Get-Date) -lt $deadline) { Start-Sleep 1 }
Get-LoggerProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$start = (Get-Date).AddMinutes(-2).ToString('yyyy-MM-ddTHH:mm:ss')
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>ow_logger install.ps1</Author>
    <Description>Overwatch session logger (ow_logger). Idle unless $Target is running; then records raw keyboard/mouse input + a 20 fps 480p screen video to $OutDir. Heartbeat: $OutDir\status.json. Disable: schtasks /end /tn $TaskName and schtasks /change /tn $TaskName /disable (or create $OutDir\DISABLED). Supervision = past TimeTrigger repeating PT1M forever + IgnoreNew.</Description>
    <URI>\$TaskName</URI>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>$sid</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <Priority>5</Priority>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>$start</StartBoundary>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
    <LogonTrigger>
      <StartBoundary>$start</StartBoundary>
    </LogonTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>"$Py"</Command>
      <Arguments>"$AppDir\logger.py" --target $Target --out "$OutDir"</Arguments>
    </Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskName $TaskName -Xml $xml -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep 8
$info = schtasks /query /tn $TaskName /v /fo list | Select-String 'Status:|Next Run Time:|Last Result:|Logon Mode:' | Select-Object -First 4
$info
if (($info | Select-String 'Next Run Time:') -match 'N/A') { throw "Next Run Time is N/A: supervision is NOT armed" }
$procs = @(Get-LoggerProcs)
if ($procs.Count -ne 1) { throw "expected exactly 1 logger process, found $($procs.Count)" }
"logger pid $($procs[0].ProcessId)"
if (-not (Test-Path "$OutDir\status.json")) { throw "logger did not write $OutDir\status.json" }
Get-Content "$OutDir\status.json" -TotalCount 6
