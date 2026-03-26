$ErrorActionPreference = "Stop"

# Avoid deleting an existing venv that may be locked by a running process.
# Instead, use a dedicated venv created with Python 3.12.
$venvDir = ".venv312"
$venvPython = Join-Path $venvDir "Scripts\\python.exe"

$needVenv = $true
if (Test-Path $venvPython) {
  $ver = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  if ($ver -eq "3.12") {
    $needVenv = $false
  }
}

if ($needVenv) {
  if (Test-Path $venvDir) {
    Remove-Item $venvDir -Recurse -Force -ErrorAction SilentlyContinue
  }
  py -3.12 -m venv $venvDir
}

& (Join-Path $venvDir "Scripts\\Activate.ps1")

python -m pip install -r requirements.txt

python .\scripts\refresh.py --scrape

$port = 8000
$probe = cmd /c "netstat -ano | findstr :$port"
if ($LASTEXITCODE -eq 0 -and $probe) {
  $port = 8001
}

uvicorn app.main:app --reload --port $port

