# Windows one-click exam demo: LocalTunnel + Streamlit
# Usage (from repo root):
#   .\scripts\demo\Start-ExamDemo.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "ERROR: .venv not found. Create with: python -m venv .venv"
    Write-Host "Then: .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host "Starting exam demo from $Root"
& $Py -u (Join-Path $Root "scripts\demo\start_exam.py")
exit $LASTEXITCODE
