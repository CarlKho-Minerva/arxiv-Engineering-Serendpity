# install_task.ps1 -Name Streams-Step0 -Cmd D:\streams\run_step0.cmd
# Supervised hidden task: TimeTrigger in the past + repeat every minute forever + IgnoreNew (see windows-task-supervision).
param([Parameter(Mandatory=$true)][string]$Name, [Parameter(Mandatory=$true)][string]$Cmd)
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument ('//B //Nologo "C:\Users\Carlk\hidden.vbs" "' + $Cmd + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-2) -RepetitionInterval (New-TimeSpan -Minutes 1)
$trigger.Repetition.StopAtDurationEnd = $false
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 7) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId 'Carlk' -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $Name
Start-Sleep -Seconds 5
$i = Get-ScheduledTaskInfo -TaskName $Name
"{0}: state={1} lastRun={2} nextRun={3} lastResult={4}" -f $Name, (Get-ScheduledTask -TaskName $Name).State, $i.LastRunTime, $i.NextRunTime, $i.LastTaskResult
