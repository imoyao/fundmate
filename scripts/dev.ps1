<#
.SYNOPSIS
    Duoduobei local dev launcher (Windows / native PowerShell)

.DESCRIPTION
    Starts backend Flask and frontend Vite, each in its own window (ASCII titles to avoid codepage issues):
      - backend: pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
      - frontend: pnpm dev  (default :8848; vite proxies /api to 127.0.0.1:8000)
    Ctrl+C cleans up both process trees.
    Note: launched via cmd.exe /c so PATH and .cmd wrappers (e.g. pnpm.cmd) resolve correctly.

.PARAMETER Install
    Run pdm install / pnpm install first (first run or after dependency changes).

.EXAMPLE
    .\scripts\dev.ps1
    .\scripts\dev.ps1 -Install
#>
param(
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Root      = Split-Path -Parent $ScriptDir
$Backend   = Join-Path $Root 'backend'
$Frontend  = Join-Path $Root 'frontend'

# Fail fast with a clear message if the inferred paths are wrong
if (-not (Test-Path $Backend))  { Write-Error "Backend directory not found: $Backend";  exit 1 }
if (-not (Test-Path $Frontend)) { Write-Error "Frontend directory not found: $Frontend"; exit 1 }

# Dependency check via cmd /c where (resolves pdm.exe and pnpm.cmd correctly)
function Assert-Command {
    param([string]$Name)
    cmd /c "where $Name >nul 2>nul"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Command '$Name' not found. Backend needs pdm, frontend needs pnpm; install them and add to PATH."
        exit 1
    }
}

Assert-Command pdm
Assert-Command pnpm

$procs = @()

try {
    if ($Install) {
        Write-Host '[Duoduobei] Installing backend deps (pdm install)...' -ForegroundColor Cyan
        $i1 = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Backend -ArgumentList '/c','pdm install' -PassThru -Wait
        if ($i1.ExitCode -ne 0) { throw 'pdm install failed' }

        Write-Host '[Duoduobei] Installing frontend deps (pnpm install)...' -ForegroundColor Cyan
        $i2 = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Frontend -ArgumentList '/c','pnpm install' -PassThru -Wait
        if ($i2.ExitCode -ne 0) { throw 'pnpm install failed' }
    }

    Write-Host '[Duoduobei] Starting backend Flask (http://localhost:8000) ...' -ForegroundColor Green
    $be = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Backend `
        -ArgumentList '/c','title Duoduobei-Backend-8000 && (pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000 || pause)' `
        -PassThru
    $procs += $be

    Write-Host '[Duoduobei] Starting frontend Vite (http://localhost:8848) ...' -ForegroundColor Green
    $fe = Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Frontend `
        -ArgumentList '/c','title Duoduobei-Frontend-8848 && (pnpm dev || pause)' `
        -PassThru
    $procs += $fe

    Write-Host ''
    Write-Host 'Backend API docs: http://localhost:8000/docs' -ForegroundColor Yellow
    Write-Host 'Frontend page:    http://localhost:8848' -ForegroundColor Yellow
    Write-Host 'Backend / frontend each open a separate window (see titles above).' -ForegroundColor Yellow
    Write-Host 'Press Ctrl+C to stop all services...' -ForegroundColor Yellow

    while ($true) { Start-Sleep -Seconds 1 }
}
finally {
    Write-Host ''
    Write-Host '[Duoduobei] Stopping services and cleaning process tree...' -ForegroundColor Red
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -Recurse } catch { }
        }
    }
    Write-Host '[Duoduobei] Stopped.' -ForegroundColor Red
}
