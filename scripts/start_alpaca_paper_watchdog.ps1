$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Runtime, $Logs | Out-Null

$PidFile = Join-Path $Runtime "alpaca_paper_watchdog.pid"
if (Test-Path $PidFile) {
  $ExistingPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
  if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
    Write-Output "watchdog already running pid=$ExistingPid"
    exit 0
  }
}

$Watchdog = Join-Path $Root "scripts\run_alpaca_paper_watchdog.ps1"
$OutLog = Join-Path $Logs "alpaca_paper_watchdog.stdout.log"
$ErrLog = Join-Path $Logs "alpaca_paper_watchdog.stderr.log"

$Process = Start-Process -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Watchdog) `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $OutLog `
  -RedirectStandardError $ErrLog `
  -PassThru

Write-Output "started watchdog pid=$($Process.Id)"
