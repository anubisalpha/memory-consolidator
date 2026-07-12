@echo off
REM Find consolidation candidates across ALL configured areas.
REM Usage: scripts\cross-check.bat
setlocal
cd /d "%~dp0.."

python main.py cross-check
