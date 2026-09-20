$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ProjectRoot "data\money_agent_daemon.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "[MONEY_AGENT] 24-hour scanner is not running."
    exit 0
}

$DaemonPid = [int](Get-Content $PidFile -Raw).Trim()
$Process = Get-CimInstance Win32_Process -Filter "ProcessId = $DaemonPid" -ErrorAction SilentlyContinue

if ($null -eq $Process) {
    Remove-Item $PidFile -Force
    Write-Host "[MONEY_AGENT] Removed a stale PID file."
    exit 0
}

if ($Process.CommandLine -notmatch "money_agent\.daemon") {
    throw "PID $DaemonPid is not MONEY_AGENT. Refusing to stop an unrelated process."
}

Stop-Process -Id $DaemonPid -Force
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "[MONEY_AGENT] 24-hour scanner stopped."
