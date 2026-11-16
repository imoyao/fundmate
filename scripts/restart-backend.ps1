<#
.SYNOPSIS
    Restart ONLY the local Flask backend (dev). Reload is ON by default.

.DESCRIPTION
    Why this script exists
    ----------------------
    `flask run --no-reload` keeps serving the code that was loaded when the process
    started, so anything merged later silently does not exist. Real case
    (2026-11-16): a backend started at 14:04, `kind='recompute'` (issue #3134)
    landed at 21:03; the new frontend then sent that payload to a backend that had
    never heard of it, the old `if/elif` fallback treated it as "supplement a buy",
    and the user saw "quantity must be greater than 0" for a button that only
    rewrites position shares. Worse: with `quantity` in the payload it would have
    written a real buy transaction.

    So the dev default here is **reload ON** (`--debug`, the same flag pair as
    `scripts/dev.ps1` and `pdm run api`). `-NoReload` stays available but is opt-in
    and spelled out explicitly -- a frozen backend is a deliberate choice, never an
    accident of whoever typed the command.

    Kept ASCII-only on purpose: Windows PowerShell 5.1 reads .ps1 without a BOM as
    ANSI, and non-ASCII literals turn into mojibake (or syntax errors) there.

.PARAMETER Port
    Port to free and re-bind. Default 8000.

.PARAMETER NoReload
    Start with --no-reload (frozen code: edits will NOT take effect until the next
    restart). Not the default; only for cases that genuinely need one frozen process.

.PARAMETER Force
    Kill whatever owns the port even when it does not look like a Python/Flask process.

.PARAMETER TimeoutSec
    Seconds to wait for /api/health before reporting "started but not healthy". Default 40.

.EXAMPLE
    .\scripts\restart-backend.ps1

.EXAMPLE
    .\scripts\restart-backend.ps1 -Port 8001

.EXAMPLE
    .\scripts\restart-backend.ps1 -NoReload
#>
param(
    [int]$Port = 8000,
    [switch]$NoReload,
    [switch]$Force,
    [int]$TimeoutSec = 40
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Root      = Split-Path -Parent $ScriptDir
$Backend   = Join-Path $Root 'backend'

if (-not (Test-Path $Backend)) { Write-Error "Backend directory not found: $Backend"; exit 1 }

cmd /c "where pdm >nul 2>nul"
if ($LASTEXITCODE -ne 0) { Write-Error "Command 'pdm' not found. Install it and add to PATH."; exit 1 }

function Get-PortOwners {
    param([int]$P)
    $conns = Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    $conns | Select-Object -ExpandProperty OwningProcess -Unique
}

function Wait-PortFree {
    param([int]$P, [int]$Seconds = 10)
    for ($i = 0; $i -lt $Seconds; $i++) {
        if ((Get-PortOwners -P $P).Count -eq 0) { return $true }
        Start-Sleep -Seconds 1
    }
    return ((Get-PortOwners -P $P).Count -eq 0)
}

# ---------- 1) free the port ----------
$owners = Get-PortOwners -P $Port
foreach ($ownerPid in $owners) {
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    $looksLikeBackend = $proc.ProcessName -match '^(python|pythonw|flask)$'
    if (-not $looksLikeBackend -and -not $Force) {
        Write-Error "Port $Port is owned by '$($proc.ProcessName)' (PID $ownerPid), not a Python/Flask process. Re-run with -Force if that is really the old backend."
        exit 1
    }
    Write-Host "[restart-backend] Stopping $($proc.ProcessName) (PID $ownerPid) on port $Port ..." -ForegroundColor Yellow
    cmd /c "taskkill /PID $ownerPid /T /F >nul 2>nul"
}

if (-not (Wait-PortFree -P $Port)) {
    Write-Error "Port $Port is still busy after killing the owners. Check manually: Get-NetTCPConnection -LocalPort $Port"
    exit 1
}

# ---------- 2) start with the right reload mode ----------
$modeFlags = if ($NoReload) { '--no-reload' } else { '--debug' }
$reloadText = if ($NoReload) {
    'reload OFF (--no-reload): this process serves FROZEN code; restart after every edit'
} else {
    'reload ON (--debug): code changes take effect automatically'
}

$cmdLine = "title Duoduobei-Backend-$Port && (pdm run flask --app app.main:app run $modeFlags --host 0.0.0.0 --port $Port || pause)"
Start-Process -FilePath 'cmd.exe' -WorkingDirectory $Backend -ArgumentList '/c', $cmdLine | Out-Null

Write-Host "[restart-backend] Backend starting on http://localhost:$Port  ->  $reloadText" -ForegroundColor Green

# ---------- 3) wait for health ----------
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 800
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($resp.status) {
            $healthy = $true
            Write-Host "[restart-backend] Health: $($resp.status) (database=$($resp.components.database.status))" -ForegroundColor Green
            break
        }
    } catch {
        # window just opened / routes not bound yet: keep polling
    }
}

if (-not $healthy) {
    Write-Warning "[restart-backend] Backend did not answer /api/health within $TimeoutSec s. Check the backend window for details (exit code 4 = another instance still holds data/app_instance.lock)."
    exit 2
}

Write-Host "[restart-backend] Done. API docs: http://localhost:$Port/docs" -ForegroundColor Yellow
