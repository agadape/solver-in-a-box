# Windows / PowerShell installer.
# Equivalent to `make install` on Unix.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "Creating venv ..." -ForegroundColor Cyan
    py -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .

Write-Host "Done. Run: scripts\run-mock.ps1" -ForegroundColor Green
