# MoodBall dev launcher: ASR (optional) + Django ASGI + Vite
# Usage: powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 [-NoBrowser]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

Write-Host "MoodBall dev launcher" -ForegroundColor Cyan
Write-Host "root: $root"

$python = Join-Path $root ".venv\Scripts\python.exe"
$daphne = Join-Path $root ".venv\Scripts\daphne.exe"
if (-not (Test-Path $python)) { throw "Missing .venv. Run: uv sync" }
if (-not (Test-Path $daphne)) { throw "Missing daphne. Run: uv sync" }

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

function Start-Bg([string]$Name, [string]$File, [object[]]$Arguments, [string]$WorkDir) {
    $outLog = Join-Path $logDir "$Name.out.log"
    $errLog = Join-Path $logDir "$Name.err.log"
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkDir `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    Start-Sleep -Milliseconds 800
    if ($process.HasExited) {
        Write-Host "[FAIL] $Name exited immediately (code $($process.ExitCode))" -ForegroundColor Red
        if (Test-Path $errLog) { Get-Content $errLog -Tail 25 | ForEach-Object { Write-Host "  $_" } }
        return $null
    }
    Write-Host "[OK] $Name started (pid $($process.Id))" -ForegroundColor Green
    return $process
}

$pids = @{}

# ---- ASR ----
$asrPython = Join-Path $root ".venv-asr\Scripts\python.exe"
if ((Test-Path $asrPython) -and -not (Test-Port 9100)) {
    Write-Host "starting ASR on 127.0.0.1:9100 ..." -ForegroundColor DarkCyan
    $asr = Start-Bg "asr" $asrPython @("-m", "uvicorn", "asr_service.app:app", "--host", "127.0.0.1", "--port", "9100") $root
    if ($asr) {
        $pids["asr"] = $asr.Id
        Write-Host "waiting for ASR model (first load may take 10-60s) ..." -ForegroundColor DarkGray
        if (Wait-Http "http://127.0.0.1:9100/health" 90) {
            Write-Host "[OK] ASR ready" -ForegroundColor Green
        } else {
            Write-Warning "ASR health check timed out; see logs/asr.err.log"
        }
    }
} elseif (Test-Port 9100) {
    Write-Host "[SKIP] ASR already listening on 9100" -ForegroundColor Yellow
} else {
    Write-Warning "No .venv-asr; ASR and wake word are unavailable. PTT/text still work."
}

# ---- Django ----
if (-not (Test-Port 8000)) {
    Write-Host "starting Django ASGI on 127.0.0.1:8000 ..." -ForegroundColor DarkCyan
    $django = Start-Bg "django" $daphne @("-b", "127.0.0.1", "-p", "8000", "moodball.asgi:application") $root
    if ($django) { $pids["django"] = $django.Id }
} else {
    Write-Host "[SKIP] Django already listening on 8000" -ForegroundColor Yellow
}

if (-not (Wait-Http "http://127.0.0.1:8000/api/health/" 25)) {
    Write-Warning "Django health check failed; see logs/django.err.log"
} else {
    Write-Host "[OK] Django ready" -ForegroundColor Green
}

# ---- Vite ----
$web = Join-Path $root "web"
$viteReady = $false
if (-not (Test-Path (Join-Path $web "node_modules"))) {
    Write-Warning "web/node_modules missing. Run: cd web; pnpm install"
} elseif (Test-Port 5173) {
    Write-Host "[SKIP] Vite already listening on 5173" -ForegroundColor Yellow
    $viteReady = $true
} else {
    Write-Host "starting Vite on http://127.0.0.1:5173 ..." -ForegroundColor DarkCyan
    $pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $pnpm) { $pnpm = (Get-Command pnpm -ErrorAction SilentlyContinue).Source }
    if ($pnpm) {
        $vite = Start-Bg "vite" $pnpm @("dev") $web
    } else {
        Write-Warning "pnpm not found on PATH; using cmd.exe"
        $vite = Start-Bg "vite" "cmd.exe" @("/c", "pnpm dev") $web
    }
    if ($vite) { $pids["vite"] = $vite.Id }
    $viteReady = Wait-Http "http://127.0.0.1:5173/" 35
    if ($viteReady) { Write-Host "[OK] Vite ready" -ForegroundColor Green }
    else { Write-Warning "Vite health check failed; see logs/vite.err.log" }
}

$pids | ConvertTo-Json | Set-Content -Encoding ASCII (Join-Path $root ".dev-pids.json")

$frontUrl = if ($viteReady) { "http://127.0.0.1:5173" } else { "http://127.0.0.1:8000" }
Write-Host ""
Write-Host "MoodBall is ready:" -ForegroundColor Green
Write-Host "  UI:     $frontUrl"
Write-Host "  API:    http://127.0.0.1:8000/api/health/"
Write-Host "  ASR:    http://127.0.0.1:9100/health"
Write-Host "  logs:   $logDir"
Write-Host "  stop:   powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1"

if (-not $NoBrowser) { Start-Process $frontUrl }

# Force the launcher to return even when stdout is captured by a parent process
# (some grandchildren keep the inherited console handle open).
exit 0
