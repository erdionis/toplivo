# Запуск мониторинга заправок в фоне
# Параметры:
#   -IntervalMinutes - интервал опроса (по умолчанию 30 минут)

param(
    [int]$IntervalMinutes = 60
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir "monitor.pid"
$LogDir = Join-Path $ScriptDir "logs"
$PythonW = "C:\Program Files\PyManager\pythonw.exe"
$MonitorScript = Join-Path $ScriptDir "monitor.py"

# Проверяем pythonw
if (-not (Test-Path $PythonW)) {
    Write-Host "ОШИБКА: pythonw.exe не найден" -ForegroundColor Red
    exit 1
}

# Проверяем скрипт
if (-not (Test-Path $MonitorScript)) {
    Write-Host "ОШИБКА: monitor.py не найден" -ForegroundColor Red
    exit 1
}

# Останавливаем предыдущий экземпляр если запущен
if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid) {
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            Write-Host "Остановлен предыдущий экземпляр (PID $oldPid)" -ForegroundColor Yellow
        }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# Создаём директорию для логов
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Запускаем в фоне через pythonw (без окна)
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "monitor_$timestamp.log"
$args = "`"$MonitorScript`" --loop $IntervalMinutes"

$process = Start-Process -FilePath $PythonW -ArgumentList $args -WorkingDirectory $ScriptDir -WindowStyle Hidden -PassThru

# Сохраняем PID
$process.Id | Out-File -FilePath $PidFile -Encoding ascii -Force

Write-Host "Monitor started" -ForegroundColor Green
Write-Host "  PID: $($process.Id)"
Write-Host "  Interval: every $IntervalMinutes min"
Write-Host "  Log: $LogFile"
Write-Host "  Stop: .\stop_monitor.ps1"
