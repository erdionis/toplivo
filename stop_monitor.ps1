# Остановка мониторинга заправок

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir "monitor.pid"

if (Test-Path $PidFile) {
    $monitorPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($monitorPid) {
        $proc = Get-Process -Id $monitorPid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $monitorPid -Force -ErrorAction SilentlyContinue
            Write-Host "Process stopped (PID $monitorPid)" -ForegroundColor Green
        } else {
            Write-Host "Process $monitorPid already not running" -ForegroundColor Yellow
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "No active monitor process found" -ForegroundColor Yellow
}
