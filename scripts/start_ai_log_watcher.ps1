# Start the Codex AI log watcher in the background.
$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$LogDir = Join-Path $RepoRoot '.ai-log'
$PidFile = Join-Path $LogDir 'codex-watcher.pid'
$OutLog = Join-Path $LogDir 'codex-watcher.out.log'
$ErrLog = Join-Path $LogDir 'codex-watcher.err.log'

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

if (Test-Path $PidFile) {
    $existingPid = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($existingPid) {
        $existing = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "[ai-log] Codex watcher is already running (PID $existingPid)."
            exit 0
        }
    }
}

$PythonCmd = if (Get-Command py -ErrorAction SilentlyContinue) {
    'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    'python'
} else {
    throw "Python launcher not found."
}

$ArgList = if ($PythonCmd -eq 'py') {
    @(
        '-3',
        (Join-Path $RepoRoot 'scripts\log_codex.py'),
        '--loop',
        '--submit',
        '--interval',
        '10'
    )
} else {
    @(
        (Join-Path $RepoRoot 'scripts\log_codex.py'),
        '--loop',
        '--submit',
        '--interval',
        '10'
    )
}

$proc = Start-Process `
    -FilePath $PythonCmd `
    -ArgumentList $ArgList `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Set-Content -Path $PidFile -Value $proc.Id -NoNewline
Write-Host "[ai-log] Codex watcher started (PID $($proc.Id))."
