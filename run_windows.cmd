@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  py -m venv .venv
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :error
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -m pip install -e . --disable-pip-version-check >nul
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m yolo_annotator_desktop %*
exit /b %errorlevel%

:error
echo.
echo Setup failed. Install Python 3.10 or newer, then run this file again.
pause
exit /b 1
