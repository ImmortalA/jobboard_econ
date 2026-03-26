$ErrorActionPreference = "Stop"

# Auto workflow:
# 1) Stop any existing server on common ports
# 2) Scrape LinkedIn via jobsparser + import into SQLite
# 3) Export the current filtered board as a static site
# 4) Start FastAPI/uvicorn on the first free port
# 5) Open the homepage in the default browser

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$venvPython = Join-Path $repoRoot ".venv312\Scripts\python.exe"
if (!(Test-Path $venvPython)) {
  throw "Missing Python: $venvPython"
}

$resultsWanted = 100
$hoursOld = 720 # ~30 days
$outputDir = Join-Path $repoRoot "data\linkedin"
$distDir = Join-Path $repoRoot "dist"
$scrapeTimeoutSeconds = 500

$portsToKill = @(8000, 8001, 8002, 8010, 8011, 8012, 8020)
$candidatePorts = @(8000, 8001, 8002, 8010, 8011, 8012, 8020)

function Stop-PortProcesses {
  param([int[]]$ports)

  foreach ($p in $ports) {
    try {
      $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
      if ($null -eq $conns) { continue }

      $pids = $conns.OwningProcess | Sort-Object -Unique
      foreach ($pid in $pids) {
        if ($pid -and $pid -ne 0) {
          Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
      }
    } catch {
      # Ignore if Get-NetTCPConnection is not available
    }
  }
}

function Is-PortFree {
  param([int]$port)

  try {
    $probe = Test-NetConnection -ComputerName "127.0.0.1" -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue
    # If probe is true, the port is already accepting connections.
    return (-not $probe)
  } catch {
    # If we can't probe, assume it's not free to be safe.
    return $false
  }
}

function Wait-For-Http200 {
  param(
    [string]$url,
    [int]$timeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
        return $true
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  return $false
}

Write-Host "Stopping servers on ports: $($portsToKill -join ', ')"
Stop-PortProcesses -ports $portsToKill

Write-Host "Scraping LinkedIn and importing..."
& $venvPython .\scripts\refresh.py --scrape `
  --results-wanted $resultsWanted `
  --hours-old $hoursOld `
  --scrape-timeout-seconds $scrapeTimeoutSeconds `
  --output-dir $outputDir

Write-Host "Exporting static site to $distDir ..."
& $venvPython .\scripts\export_static.py --output-dir $distDir

$portToUse = $null
foreach ($p in $candidatePorts) {
  if (Is-PortFree -port $p) {
    $portToUse = $p
    break
  }
}

if ($null -eq $portToUse) {
  throw "No free port found from: $($candidatePorts -join ', ')"
}

Write-Host "Starting uvicorn on port $portToUse ..."
Start-Process -FilePath $venvPython -ArgumentList @(
  "-m", "uvicorn", "app.main:app",
  "--reload",
  "--host", "127.0.0.1",
  "--port", "$portToUse"
) -NoNewWindow

$url = "http://127.0.0.1:$portToUse/"
Write-Host "Waiting for server at $url ..."
$ok = Wait-For-Http200 -url ("http://127.0.0.1:$portToUse/api/jobs") -timeoutSeconds 45
if (-not $ok) {
  Write-Host "Server did not become ready within the timeout. Trying to open anyway: $url"
}

Start-Process $url
Write-Host "Done."

