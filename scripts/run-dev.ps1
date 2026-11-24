param(
  [int]$BackendPort = 4000,
  [int]$FrontendPort = 5173,
  [int]$BackendWorkers = 2,
  [switch]$Reload
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) {
  $python = Get-Command python -ErrorAction SilentlyContinue
}

if (-not $npm) {
  throw "npm.cmd was not found on PATH. Install Node.js first, then rerun this command."
}
if (-not $python) {
  throw "python was not found on PATH. Install Python or activate your virtual environment first."
}

if ($BackendWorkers -lt 1) {
  throw "BackendWorkers must be at least 1."
}

if ($Reload -and $BackendWorkers -gt 1) {
  Write-Host "[backend] --reload requires a single worker. Using BackendWorkers=1." -ForegroundColor Yellow
  $BackendWorkers = 1
}

function Ensure-Dependencies($Name, $Dir) {
  $nodeModules = Join-Path $Dir "node_modules"
  if (Test-Path $nodeModules) {
    return
  }

  Write-Host "[$Name] node_modules not found. Running npm install..." -ForegroundColor Yellow
  Push-Location $Dir
  try {
    & $npm.Source install
    if ($LASTEXITCODE -ne 0) {
      throw "npm install failed for $Name."
    }
  } finally {
    Pop-Location
  }
}

function Start-DevProcess($Name, $Dir, $FileName, [string[]]$Arguments, $EnvVars = @{}) {
  $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $FileName
  $startInfo.WorkingDirectory = $Dir
  $startInfo.Arguments = ($Arguments | ForEach-Object {
    if ($_ -match '[\s"]') {
      '"' + ($_ -replace '"', '\"') + '"'
    } else {
      $_
    }
  }) -join " "
  $startInfo.UseShellExecute = $false
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  $startInfo.CreateNoWindow = $true

  foreach ($key in $EnvVars.Keys) {
    $startInfo.Environment[$key] = [string]$EnvVars[$key]
  }

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $startInfo
  $process.EnableRaisingEvents = $true

  $outputHandler = [System.Diagnostics.DataReceivedEventHandler]{
    param($sender, $event)
    if ($event.Data) {
      Write-Host "[$Name] $($event.Data)"
    }
  }
  $errorHandler = [System.Diagnostics.DataReceivedEventHandler]{
    param($sender, $event)
    if ($event.Data) {
      Write-Host "[$Name] $($event.Data)" -ForegroundColor Red
    }
  }

  $process.add_OutputDataReceived($outputHandler)
  $process.add_ErrorDataReceived($errorHandler)

  if (-not $process.Start()) {
    throw "Could not start $Name."
  }

  $process.BeginOutputReadLine()
  $process.BeginErrorReadLine()
  return $process
}

Ensure-Dependencies "frontend" $frontendDir

$backendApi = "http://localhost:$BackendPort"
$processes = @()

try {
  Write-Host "Starting StudyFlow..." -ForegroundColor Cyan
  Write-Host "Backend:  $backendApi ($BackendWorkers worker$(if ($BackendWorkers -eq 1) { '' } else { 's' }))"
  Write-Host "Frontend: http://localhost:$FrontendPort"
  Write-Host "Press Ctrl+C to stop both servers." -ForegroundColor DarkGray

  $backendArgs = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$BackendPort")
  if ($BackendWorkers -gt 1) {
    $backendArgs += @("--workers", "$BackendWorkers")
  }
  if ($Reload) {
    $backendArgs += "--reload"
  }

  $processes += Start-DevProcess "backend" $backendDir $python.Source $backendArgs @{
    PORT = $BackendPort
  }
  $processes += Start-DevProcess "frontend" $frontendDir $npm.Source @("run", "dev", "--", "--host", "0.0.0.0", "--port", $FrontendPort) @{}

  while ($true) {
    $exited = $processes | Where-Object { $_.HasExited }
    if ($exited) {
      $names = $exited | ForEach-Object { $_.Id }
      throw "A dev process exited unexpectedly. Process id(s): $($names -join ', ')."
    }
    Start-Sleep -Milliseconds 500
  }
} finally {
  Write-Host "Stopping StudyFlow dev servers..." -ForegroundColor Yellow
  foreach ($process in $processes) {
    if ($process -and -not $process.HasExited) {
      try {
        $process.Kill($true)
      } catch [System.Management.Automation.MethodException] {
        $process.Kill()
      }
      $process.WaitForExit()
    }
    if ($process) {
      $process.Dispose()
    }
  }
}
