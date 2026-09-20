@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$path=Join-Path ([Environment]::GetFolderPath('Startup')) 'MONEY_AGENT 24H.lnk';" ^
  "Remove-Item $path -Force -ErrorAction SilentlyContinue"
echo [MONEY_AGENT] Windows startup entry removed.
pause
