$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$StopFile = Join-Path $Runtime "alpaca_paper_supervisor.stop"
$PidFile = Join-Path $Runtime "alpaca_paper_supervisor.pid"

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Set-Content -LiteralPath $StopFile -Value (Get-Date -Format o)

if (Test-Path -LiteralPath $PidFile) {
  $existingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
    Write-Output "stop requested for supervisor pid=$existingPid"
    exit 0
  }
}

Write-Output "stop requested; no running supervisor pid found"
