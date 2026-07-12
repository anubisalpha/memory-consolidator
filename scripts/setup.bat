@echo off
REM Install runtime + test dependencies. Run from anywhere.
setlocal
cd /d "%~dp0.."

python -m pip install pyyaml pytest
if errorlevel 1 (
    echo Setup failed.
    exit /b 1
)
echo Setup complete. Try: scripts\audit.bat
