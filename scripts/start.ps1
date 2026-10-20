# Start the built MoodBall app: migrate + build if needed + Daphne + browser.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv. Run: uv sync" }

Write-Host "applying migrations ..." -ForegroundColor DarkCyan
& $python manage.py migrate --noinput
& $python manage.py check

$index = Join-Path $root "web\dist\index.html"
if (-not (Test-Path $index)) {
    Write-Warning "web/dist missing; building frontend ..."
    Push-Location (Join-Path $root "web")
    try {
        pnpm install
        pnpm build
    } finally {
        Pop-Location
    }
}

$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

Write-Host "starting MoodBall on http://127.0.0.1:8000 ..." -ForegroundColor Green
Start-Process -FilePath (Join-Path $root ".venv\Scripts\daphne.exe") `
    -ArgumentList "-b", "127.0.0.1", "-p", "8000", "moodball.asgi:application" `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir "django.out.log") `
    -RedirectStandardError (Join-Path $logDir "django.err.log")
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8000"
