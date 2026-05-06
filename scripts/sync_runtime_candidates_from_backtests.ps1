Param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Write-JsonFile {
  Param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)]$Object
  )
  $dir = Split-Path -Parent $Path
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
  ($Object | ConvertTo-Json -Depth 10) | Set-Content -Path $Path -Encoding UTF8
}

function Parse-MdTableRows {
  Param(
    [string[]]$Lines = @()
  )
  $rows = @()
  foreach ($line in $Lines) {
    $trim = $line.Trim()
    if (-not $trim.StartsWith("|")) { continue }
    if ($trim -match "^\|\s*---") { continue }
    $parts = $trim.Trim("|").Split("|") | ForEach-Object { $_.Trim() }
    if ($parts.Count -lt 3) { continue }
    if ($parts[0].ToLowerInvariant() -eq "rank") { continue }
    $rows += ,$parts
  }
  return $rows
}

$null = $null
function Get-Col {
  Param(
    [Parameter(Mandatory = $true)]$Row,
    [Parameter(Mandatory = $true)][int]$Index
  )
  if ($null -eq $Row) { return "" }
  if ($Row.Count -le $Index) { return "" }
  $value = $Row[$Index]
  if ($null -eq $value) { return "" }
  return [string]$value
}

$runtimeDir = Join-Path $Root "runtime"
$docsDir = Join-Path $Root "docs\\backtests"

$rankingsMd = Join-Path $docsDir "strategy-rankings.md"
$topSignalMd = Join-Path $docsDir "top-signal-report.md"

if (-not (Test-Path $rankingsMd)) { throw "Missing $rankingsMd" }
if (-not (Test-Path $topSignalMd)) { throw "Missing $topSignalMd" }

$now = (Get-Date).ToUniversalTime().ToString("o")

# strategy_rankings.json
$rankingsLines = Get-Content -Path $rankingsMd -Encoding UTF8
$rankingsRows = Parse-MdTableRows -Lines $rankingsLines
$ranked = @()
foreach ($row in $rankingsRows) {
  # Expected columns: Rank | Symbol | Pass | Score | ...
  $rank = 0
  [void][int]::TryParse((Get-Col -Row $row -Index 0), [ref]$rank)
  $symbol = (Get-Col -Row $row -Index 1).ToUpperInvariant()
  $passRaw = (Get-Col -Row $row -Index 2).ToLowerInvariant()
  $pass = $passRaw -in @("yes", "true", "1")
  $score = $null
  $scoreRaw = (Get-Col -Row $row -Index 3)
  $scoreValue = 0.0
  if ([double]::TryParse($scoreRaw, [ref]$scoreValue)) { $score = $scoreValue }
  if (-not $symbol) { continue }
  $ranked += [ordered]@{
    rank   = $rank
    symbol = $symbol
    pass   = $pass
    score  = $score
  }
}

$strategyRankingsPayload = [ordered]@{
  generated_at = $now
  source       = "docs/backtests/strategy-rankings.md"
  ranked       = $ranked
}
Write-JsonFile -Path (Join-Path $runtimeDir "strategy_rankings.json") -Object $strategyRankingsPayload

# active_paper_candidates.json (actionable allowlist)
$topSignalLines = Get-Content -Path $topSignalMd -Encoding UTF8
$topSignalRows = Parse-MdTableRows -Lines $topSignalLines
$active = @()
foreach ($row in $topSignalRows) {
  # Expected columns: Rank | Symbol | Actionable | Decision | Score | ...
  $rank = 0
  [void][int]::TryParse((Get-Col -Row $row -Index 0), [ref]$rank)
  $symbol = (Get-Col -Row $row -Index 1).ToUpperInvariant()
  $actionableRaw = (Get-Col -Row $row -Index 2).ToLowerInvariant()
  $actionable = $actionableRaw -in @("yes", "true", "1")
  if (-not $actionable) { continue }
  $decision = Get-Col -Row $row -Index 3
  $score = $null
  $scoreRaw = Get-Col -Row $row -Index 4
  $scoreValue = 0.0
  if ([double]::TryParse($scoreRaw, [ref]$scoreValue)) { $score = $scoreValue }
  if (-not $symbol) { continue }
  $active += [ordered]@{
    rank      = $rank
    symbol    = $symbol
    decision  = $decision
    score     = $score
    actionable = $true
  }
}

$activeCandidatesPayload = [ordered]@{
  generated_at = $now
  source       = "docs/backtests/top-signal-report.md"
  active       = $active
}
Write-JsonFile -Path (Join-Path $runtimeDir "active_paper_candidates.json") -Object $activeCandidatesPayload

Write-Output (Join-Path $runtimeDir "strategy_rankings.json")
Write-Output (Join-Path $runtimeDir "active_paper_candidates.json")
