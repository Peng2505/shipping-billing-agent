# Stop exam demo processes recorded for THIS project only.
# Usage (from repo root):
#   .\scripts\demo\Stop-ExamDemo.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "ERROR: .venv python missing"
    exit 1
}

& $Py -u (Join-Path $Root "scripts\demo\stop_exam.py")
exit $LASTEXITCODE
