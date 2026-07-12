@echo off
REM Install runtime + test dependencies. Run from anywhere.
setlocal
cd /d "%~dp0.."

python -m pip install -r requirements-dev.txt
if errorlevel 1 (
    echo Setup failed.
    exit /b 1
)
echo Setup complete. Try: scripts\audit.bat
