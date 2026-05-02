$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Runtime, $Logs | Out-Null

$PidFile = Join-Path $Runtime "alpaca_paper_watchdog.pid"
$StopFile = Join-Path $Runtime "alpaca_paper_watchdog.stop"
$LogFile = Join-Path $Logs "alpaca_paper_watchdog.log"

Set-Content -LiteralPath $PidFile -Value $PID
if (Test-Path $StopFile) {
  Remove-Item -LiteralPath $StopFile -Force
}

Set-Location $Root
"$(Get-Date -Format o) watchdog started pid=$PID" | Add-Content -LiteralPath $LogFile

while (-not (Test-Path $StopFile)) {
  "$(Get-Date -Format o) runner cycle start" | Add-Content -LiteralPath $LogFile
  python "scripts\alpaca_paper_runner.py" --once
  $exitCode = $LASTEXITCODE
  "$(Get-Date -Format o) runner exited code=$exitCode; next cycle in 300s" | Add-Content -LiteralPath $LogFile
  $slept = 0
  while ($slept -lt 300 -and -not (Test-Path $StopFile)) {
    Start-Sleep -Seconds 5
    $slept += 5
  }
}

"$(Get-Date -Format o) watchdog stopped" | Add-Content -LiteralPath $LogFile
