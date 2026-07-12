@echo off
REM Interactively resolve diverged cross-area slug conflicts into a
REM 'memory-diverged' area. Usage: scripts\resolve-conflicts.bat
setlocal
cd /d "%~dp0.."

python main.py resolve-conflicts
