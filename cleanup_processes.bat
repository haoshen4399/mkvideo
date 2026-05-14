@echo off
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" "tools\cleanup_processes.py" %*
endlocal

