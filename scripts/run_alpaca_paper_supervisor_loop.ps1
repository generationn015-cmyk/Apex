$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnsureScript = Join-Path $Root "scripts\ensure_alpaca_paper_watchdog.ps1"
$Runtime = Join-Path $Root "runtime"
$Logs = Join-Path $Root "logs"
$PidFile = Join-Path $Runtime "alpaca_paper_supervisor.pid"
$StopFile = Join-Path $Runtime "alpaca_paper_supervisor.stop"
$LogFile = Join-Path $Logs "alpaca_paper_watchdog_supervisor.log"

New-Item -ItemType Directory -Force -Path $Runtime, $Logs | Out-Null
Set-Content -LiteralPath $PidFile -Value $PID
if (Test-Path -LiteralPath $StopFile) {
  Remove-Item -LiteralPath $StopFile -Force
}

"$(Get-Date -Format o) supervisor loop started pid=$PID" | Add-Content -LiteralPath $LogFile

while (-not (Test-Path -LiteralPath $StopFile)) {
  try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EnsureScript
  } catch {
    "$(Get-Date -Format o) supervisor loop check failed: $($_.Exception.Message)" | Add-Content -LiteralPath $LogFile
  }

  $slept = 0
  while ($slept -lt 300 -and -not (Test-Path -LiteralPath $StopFile)) {
    Start-Sleep -Seconds 5
    $slept += 5
  }
}

"$(Get-Date -Format o) supervisor loop stopped" | Add-Content -LiteralPath $LogFile
