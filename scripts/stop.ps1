# Stop MoodBall dev services by recorded PIDs first, then by listening ports.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".dev-pids.json"

if (Test-Path $pidFile) {
    try {
        $recorded = Get-Content $pidFile -Raw | ConvertFrom-Json
        foreach ($property in $recorded.PSObject.Properties) {
            $procId = [int]$property.Value
            $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "stopping $($property.Name) tree (pid $procId)"
                & taskkill.exe /PID $procId /T /F 2>&1 | Out-Null
            }
        }
    } catch {
        Write-Warning "could not read .dev-pids.json: $($_.Exception.Message)"
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

foreach ($port in @(8000, 9100, 5173)) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($connection in $connections) {
            $procId = $connection.OwningProcess
            $process = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "stopping $($process.ProcessName) on :$port (pid $procId)"
                & taskkill.exe /PID $procId /T /F 2>&1 | Out-Null
            }
        }
    } catch {
        Write-Host "no listener on :$port"
    }
}

Write-Host "MoodBall dev services stopped."
