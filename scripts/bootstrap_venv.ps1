param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path -LiteralPath "requirements.lock")) {
    throw "requirements.lock not found. Run this script from the repository checkout."
}

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11+ is required. Re-run with -Python pointing to a Python 3.11+ executable."
}

& $Python -m venv .venv
& .\.venv\Scripts\python.exe -m ensurepip --upgrade
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock
& .\.venv\Scripts\python.exe -m pip install -e .

Write-Host "Virtual environment ready: .venv"
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"
