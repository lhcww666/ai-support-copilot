$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

Push-Location $root
try {
    & $python -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m pytest
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
