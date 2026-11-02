Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$engine = Resolve-Path (Join-Path $PSScriptRoot "..\engine")
$venvPython = Join-Path $engine ".venv\Scripts\python.exe"
Push-Location $engine
try {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv sync
        uv run --with pyinstaller pyinstaller packaging/eduanchor-engine.spec --noconfirm --clean
    }
    elseif (Test-Path -LiteralPath $venvPython) {
        & $venvPython -m PyInstaller packaging/eduanchor-engine.spec --noconfirm --clean
    }
    else {
        throw "Need uv or code/engine/.venv with PyInstaller installed."
    }
    Write-Host "Built: $engine\dist\eduanchor-engine"
}
finally {
    Pop-Location
}
