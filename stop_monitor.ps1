# Остановка мониторинга заправок

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir "monitor.pid"

if (Test-Path $PidFile) {
    $pid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($pid) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "Process stopped (PID $pid)" -ForegroundColor Green
        } else {
            Write-Host "Process $pid already not running" -ForegroundColor Yellow
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "No active monitor process found" -ForegroundColor Yellow
}
