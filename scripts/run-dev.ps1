$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    python -m venv (Join-Path $root '.venv')
    & $python -m pip install -e "${root}[dev]"
}

Push-Location $root
try {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
