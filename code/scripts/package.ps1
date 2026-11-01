Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$engine = Join-Path $root "engine"
$desktop = Join-Path $root "desktop"

Write-Host "==> Building Python engine"
& (Join-Path $PSScriptRoot "build-engine.ps1")

Write-Host "==> Building desktop installer"
Push-Location $desktop
if (-not (Test-Path "node_modules")) { npm install }
npm run dist
Pop-Location

Write-Host "Output: $desktop\release"
