# Windows / PowerShell runner — mock mode.
# Equivalent to `make run-mock` on Unix.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "venv missing. Run scripts\install.ps1 first." -ForegroundColor Red
    exit 1
}

& .\.venv\Scripts\Activate.ps1

$env:MODE = "mock"
$env:PYTHONUTF8 = "1"

Write-Host "Starting mock server on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$mock = Start-Process -PassThru -NoNewWindow `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","mock_server.main:app","--host","127.0.0.1","--port","8000"

Start-Sleep -Seconds 2

Write-Host "Starting solver (mock mode) ..." -ForegroundColor Cyan
try {
    & .\.venv\Scripts\python.exe -m solver.main
} finally {
    Write-Host "Stopping mock server ..." -ForegroundColor Yellow
    Stop-Process -Id $mock.Id -Force -ErrorAction SilentlyContinue
}
