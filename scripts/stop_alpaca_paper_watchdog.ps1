$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$StopFile = Join-Path $Runtime "alpaca_paper_watchdog.stop"
$PidFile = Join-Path $Runtime "alpaca_paper_watchdog.pid"

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Set-Content -LiteralPath $StopFile -Value (Get-Date -Format o)

if (Test-Path $PidFile) {
  $ExistingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
    Write-Output "stop requested for watchdog pid=$ExistingPid"
    exit 0
  }
}

Write-Output "stop requested; no running watchdog pid found"
