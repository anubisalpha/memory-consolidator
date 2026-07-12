@echo off
REM Discover memory-shaped files scattered outside a configured area's root.
REM Usage: scripts\map.bat <area-name>
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
    echo Usage: scripts\map.bat ^<area-name^>
    exit /b 1
)

python main.py map --area %1
