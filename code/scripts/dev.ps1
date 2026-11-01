Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$engine = Join-Path $root "engine"
$desktop = Join-Path $root "desktop"

Write-Host "==> Importing sample textbook into a local data directory"
$env:EDUANCHOR_DATA_DIR = Join-Path $engine ".data"
Push-Location $engine
uv sync
uv run eduanchor seed --reset
Pop-Location

Write-Host "==> Starting Electron dev app"
Push-Location $desktop
if (-not (Test-Path "node_modules")) { npm install }
npm run dev
