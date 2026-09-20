@echo off
setlocal
cd /d "%~dp0"
set "MONEY_AGENT_START=%~dp0start_24h.bat"
set "MONEY_AGENT_WORKDIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$startup=[Environment]::GetFolderPath('Startup');" ^
  "$shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startup 'MONEY_AGENT 24H.lnk'));" ^
  "$shortcut.TargetPath=$env:MONEY_AGENT_START;" ^
  "$shortcut.WorkingDirectory=$env:MONEY_AGENT_WORKDIR;" ^
  "$shortcut.WindowStyle=7;" ^
  "$shortcut.Save()"

if errorlevel 1 (
    echo [MONEY_AGENT] Startup installation failed.
    pause
    exit /b 1
)

echo [MONEY_AGENT] It will now start automatically when you sign in to Windows.
pause
