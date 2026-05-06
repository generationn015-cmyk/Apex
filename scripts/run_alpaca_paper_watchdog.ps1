$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Runtime, $Logs | Out-Null

$PidFile = Join-Path $Runtime "alpaca_paper_watchdog.pid"
$StopFile = Join-Path $Runtime "alpaca_paper_watchdog.stop"
$LogFile = Join-Path $Logs "alpaca_paper_watchdog.log"

Set-Location $Root
"$(Get-Date -Format o) watchdog started pid=$PID" | Add-Content -LiteralPath $LogFile

function Resolve-PythonCommand {
  $candidates = @()

  $candidates += (Join-Path $Root ".venv\\Scripts\\python.exe")
  $candidates += (Join-Path $Root "venv\\Scripts\\python.exe")
  $candidates += (Join-Path $Root "env\\Scripts\\python.exe")

  foreach ($path in $candidates) {
    if ($path -and (Test-Path -LiteralPath $path)) {
      return @{ FilePath = $path; Args = @() }
    }
  }

  $cmd = Get-Command -Name "python" -ErrorAction SilentlyContinue
  if ($cmd) { return @{ FilePath = $cmd.Source; Args = @() } }

  $cmd = Get-Command -Name "python3" -ErrorAction SilentlyContinue
  if ($cmd) { return @{ FilePath = $cmd.Source; Args = @() } }

  $cmd = Get-Command -Name "py" -ErrorAction SilentlyContinue
  if ($cmd) { return @{ FilePath = $cmd.Source; Args = @("-3") } }

  return $null
}

$Python = Resolve-PythonCommand
if (-not $Python) {
  "$(Get-Date -Format o) watchdog abort: python interpreter not found (tried .venv/venv/env + python/python3/py)" | Add-Content -LiteralPath $LogFile
  exit 127
}

function Get-DotEnvValue {
  param([string] $Name)
  $EnvPath = Join-Path $Root ".env"
  if (-not (Test-Path -LiteralPath $EnvPath)) {
    return ""
  }
  foreach ($line in Get-Content -LiteralPath $EnvPath) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
      continue
    }
    $parts = $trimmed.Split("=", 2)
    if ($parts[0].Trim() -eq $Name) {
      return $parts[1].Trim()
    }
  }
  return ""
}

$RunnerArgs = @("scripts\\alpaca_paper_runner.py", "--once")
$Symbols = Get-DotEnvValue "APEX_ALPACA_SYMBOLS"
if ($Symbols) {
  $RunnerArgs += @("--symbols", $Symbols)
}
$MaxNotional = Get-DotEnvValue "APEX_ALPACA_MAX_NOTIONAL"
if ($MaxNotional) {
  $RunnerArgs += @("--max-notional", $MaxNotional)
}

Set-Content -LiteralPath $PidFile -Value $PID
if (Test-Path $StopFile) {
  Remove-Item -LiteralPath $StopFile -Force
}

while (-not (Test-Path $StopFile)) {
  "$(Get-Date -Format o) runner cycle start" | Add-Content -LiteralPath $LogFile
  & $Python.FilePath @($Python.Args + $RunnerArgs)
  $exitCode = $LASTEXITCODE
  "$(Get-Date -Format o) runner exited code=$exitCode; next cycle in 300s" | Add-Content -LiteralPath $LogFile
  $slept = 0
  while ($slept -lt 300 -and -not (Test-Path $StopFile)) {
    Start-Sleep -Seconds 5
    $slept += 5
  }
}

"$(Get-Date -Format o) watchdog stopped" | Add-Content -LiteralPath $LogFile
