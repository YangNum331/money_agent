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

start "" ".venv\Scripts\pythonw.exe" -m money_agent.gui
exit /b 0

:setup_error
echo.
echo Setup failed. Install Python 3.11 or newer and try again.
pause
exit /b 1
