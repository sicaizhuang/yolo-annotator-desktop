@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call run_windows.cmd --help
".venv\Scripts\python.exe" -m unittest discover -s tests -v
pause
