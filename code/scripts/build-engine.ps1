Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$engine = Resolve-Path (Join-Path $PSScriptRoot "..\engine")
Push-Location $engine
try {
    uv sync
    uv run --with pyinstaller pyinstaller packaging/eduanchor-engine.spec --noconfirm --clean
    Write-Host "Built: $engine\dist\eduanchor-engine"
}
finally {
    Pop-Location
}
