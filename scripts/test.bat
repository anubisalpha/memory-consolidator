@echo off
REM Run the pytest suite.
setlocal
cd /d "%~dp0.."

python -m pytest tests/ -q
