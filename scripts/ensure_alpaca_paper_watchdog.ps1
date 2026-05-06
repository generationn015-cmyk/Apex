$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$Logs = Join-Path $Root "logs"
$PidFile = Join-Path $Runtime "alpaca_paper_watchdog.pid"
$HeartbeatFile = Join-Path $Runtime "alpaca_paper_runner.heartbeat"
$WatchdogScript = Join-Path $Root "scripts\run_alpaca_paper_watchdog.ps1"
$LogFile = Join-Path $Logs "alpaca_paper_watchdog_supervisor.log"
$MaxHeartbeatAgeMinutes = 10

New-Item -ItemType Directory -Force -Path $Runtime, $Logs | Out-Null

function Write-SupervisorLog {
  param([string] $Message)
  "$(Get-Date -Format o) $Message" | Add-Content -LiteralPath $LogFile
}

function Get-WatchdogProcess {
  if (-not (Test-Path -LiteralPath $PidFile)) {
    return $null
  }
  $existingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if (-not $existingPid) {
    return $null
  }
  return Get-Process -Id $existingPid -ErrorAction SilentlyContinue
}

function Get-HeartbeatAgeMinutes {
  if (-not (Test-Path -LiteralPath $HeartbeatFile)) {
    return [double]::PositiveInfinity
  }
  $lastWrite = (Get-Item -LiteralPath $HeartbeatFile).LastWriteTimeUtc
  return ((Get-Date).ToUniversalTime() - $lastWrite).TotalMinutes
}

$watchdog = Get-WatchdogProcess
$heartbeatAge = Get-HeartbeatAgeMinutes

if ($watchdog -and $heartbeatAge -le $MaxHeartbeatAgeMinutes) {
  Write-SupervisorLog "watchdog healthy pid=$($watchdog.Id) heartbeat_age_min=$([math]::Round($heartbeatAge, 2))"
  exit 0
}

if ($watchdog -and $heartbeatAge -eq [double]::PositiveInfinity) {
  $processAgeMinutes = ((Get-Date) - $watchdog.StartTime).TotalMinutes
  if ($processAgeMinutes -le $MaxHeartbeatAgeMinutes) {
    Write-SupervisorLog "watchdog starting pid=$($watchdog.Id) process_age_min=$([math]::Round($processAgeMinutes, 2)); waiting for first heartbeat"
    exit 0
  }
}

if ($watchdog) {
  Write-SupervisorLog "watchdog process exists but heartbeat stale pid=$($watchdog.Id) heartbeat_age_min=$([math]::Round($heartbeatAge, 2)); starting replacement"
} else {
  Write-SupervisorLog "watchdog missing heartbeat_age_min=$([math]::Round($heartbeatAge, 2)); starting replacement"
}

Start-Process -FilePath powershell.exe -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-File",
  "`"$WatchdogScript`""
) -WindowStyle Hidden

Start-Sleep -Seconds 5
$newWatchdog = Get-WatchdogProcess
if ($newWatchdog) {
  Write-SupervisorLog "watchdog replacement started pid=$($newWatchdog.Id)"
  exit 0
}

Write-SupervisorLog "watchdog replacement failed to start"
exit 1
