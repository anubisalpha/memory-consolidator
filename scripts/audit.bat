@echo off
REM Audit every configured area (or one, if a name is passed).
REM Usage: scripts\audit.bat [area-name]
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
    python main.py audit
) else (
    python main.py audit --area %1
)
