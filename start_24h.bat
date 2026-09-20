@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [MONEY_AGENT] First-time setup...
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto :setup_error
)

if not exist ".venv\.money_agent_ready" (
    ".venv\Scripts\python.exe" -m pip install -e . --disable-pip-version-check -q
    if errorlevel 1 goto :setup_error
    type nul > ".venv\.money_agent_ready"
)

start "" ".venv\Scripts\pythonw.exe" -m money_agent.daemon
timeout /t 2 /nobreak >nul

if exist "data\money_agent_daemon.pid" (
    echo [MONEY_AGENT] 24-hour scanner is running.
    echo Search interval: 6 hours
    echo Database: data\money_agent.db
    echo Log: logs\money_agent.log
    exit /b 0
)

echo [MONEY_AGENT] The scanner did not start. Check logs\money_agent.log.
pause
exit /b 1

:setup_error
echo.
echo Setup failed. Install Python 3.11 or newer and try again.
pause
exit /b 1
