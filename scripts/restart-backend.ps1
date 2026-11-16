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

.PARAMETER RepoRoot
    Checkout to serve. Default: the repo this script lives in. Point it at the MAIN
    checkout when running from a git worktree -- a worktree's `backend/.venv` is an
    empty shell (its `pdm run` builds a venv with no dependencies), so the backend
    started from there dies on `import flask`.

.PARAMETER Force
    Kill whatever owns the port even when it does not look like a Python/Flask process.

.PARAMETER TimeoutSec
    Seconds to wait for /api/health before reporting "started but not healthy". Default 60
    (pdm cold start plus V8 warm-up took ~20 s on the reference machine).

.EXAMPLE
    .\scripts\restart-backend.ps1

.EXAMPLE
    .\scripts\restart-backend.ps1 -RepoRoot D:\codes\fundmate

.EXAMPLE
    .\scripts\restart-backend.ps1 -Port 8001

.EXAMPLE
    .\scripts\restart-backend.ps1 -NoReload
#>
param(
    [int]$Port = 8000,
    [string]$RepoRoot,
    [switch]$NoReload,
    [switch]$Force,
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Root      = if ($RepoRoot) { (Resolve-Path $RepoRoot).Path } else { Split-Path -Parent $ScriptDir }
$Backend   = Join-Path $Root 'backend'

# Plain console line + exit 1: Write-Error under EAP=Stop throws and decorates the text
# with a stack frame, which buries the one sentence that matters.
function Fail {
    param([string]$Message)
    Write-Host "[restart-backend] ERROR: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Backend)) { Fail "Backend directory not found: $Backend" }

cmd /c "where pdm >nul 2>nul"
if ($LASTEXITCODE -ne 0) { Fail "Command 'pdm' not found. Install it and add to PATH." }

# The backend must run from `$Backend` (relative invest.db / logs / data live there),
# and that checkout's venv must actually have dependencies. Checking up front turns a
# silent crash-into-a-60 s timeout into one actionable line.
$venvPy = Join-Path $Backend '.venv/Scripts/python.exe'
if (-not (Test-Path $venvPy)) { Fail "No venv interpreter at $venvPy. Run 'pdm install' in $Backend first." }

# PS 5.1 turns a native command's stderr into an ErrorRecord; with EAP=Stop that would
# abort the script with a raw Python traceback instead of the message below.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $venvPy -c 'import flask' 2>$null | Out-Null
$importOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $importOk) {
    Fail "The venv under $Backend has no dependencies (empty shell venv -- typical for a fresh git worktree). Serve the main checkout instead: .\scripts\restart-backend.ps1 -RepoRoot D:\codes\fundmate"
}

Write-Host "[restart-backend] Repo: $Root" -ForegroundColor DarkGray
Write-Host "[restart-backend] Backend cwd: $Backend" -ForegroundColor DarkGray

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

# ---------- 1) stop the old backend ----------
# Kill the whole `cmd -> pdm -> python -m flask -> reloader child` chain, not just the
# port owner. With reload enabled the port owner is the deepest child, while the LOCK
# (data/app_instance.lock) is held by its parent -- kill only the child and the new
# instance dies with exit code 4 ("another instance holds the lock"). Walk up the parent
# chain while it still looks like our launch command, and taskkill /T the top one.
function Get-StopTargetPid {
    param([int]$StartPid)
    $killPid = $StartPid
    $cur = $StartPid
    for ($i = 0; $i -lt 5; $i++) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$cur" -ErrorAction SilentlyContinue
        if (-not $proc -or -not $proc.ParentProcessId) { break }
        $parentId = [int]$proc.ParentProcessId
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$parentId" -ErrorAction SilentlyContinue
        if (-not $parent -or -not $parent.CommandLine) { break }
        if ($parent.CommandLine -match 'flask|pdm|app\.main') {
            $killPid = $parentId
            $cur = $parentId
        } else {
            break
        }
    }
    $killPid
}

$owners = Get-PortOwners -P $Port
if ($owners.Count -gt 0) {
    $ownerProc = Get-Process -Id $owners[0] -ErrorAction SilentlyContinue
    if ($ownerProc -and $ownerProc.ProcessName -notmatch '^(python|pythonw|flask|cmd|pdm)$' -and -not $Force) {
        Fail "Port $Port is owned by '$($ownerProc.ProcessName)' (PID $($owners[0])), not a Python/Flask process. Re-run with -Force if that is really the old backend."
    }
}

$targets = $owners | ForEach-Object { Get-StopTargetPid -StartPid $_ } | Sort-Object -Unique
foreach ($targetPid in $targets) {
    $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    Write-Host "[restart-backend] Stopping $($proc.ProcessName) (PID $targetPid) ..." -ForegroundColor Yellow
    cmd /c "taskkill /PID $targetPid /T /F >nul 2>nul"
}

if (-not (Wait-PortFree -P $Port)) {
    Fail "Port $Port is still busy after killing the backend processes. Check manually: Get-NetTCPConnection -LocalPort $Port"
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
