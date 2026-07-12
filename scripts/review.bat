@echo off
REM Interactive review session for one area.
REM Usage: scripts\review.bat <area-name>
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
    echo Usage: scripts\review.bat ^<area-name^>
    exit /b 1
)

python main.py review --area %1
