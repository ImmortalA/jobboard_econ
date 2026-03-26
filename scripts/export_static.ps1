$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv312\Scripts\python.exe"
if (!(Test-Path $venvPython)) {
  throw "Missing Python: $venvPython"
}

$distDir = Join-Path $repoRoot "dist"

Write-Host "Exporting static job board to $distDir ..."
& $venvPython .\scripts\export_static.py --output-dir $distDir

$indexPath = Join-Path $distDir "index.html"
if (Test-Path $indexPath) {
  Start-Process $indexPath
}
