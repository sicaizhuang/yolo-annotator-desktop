@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\create_windows_shortcut.ps1"
if errorlevel 1 (
  echo Failed to create the shortcut.
) else (
  echo Desktop shortcut created.
)
pause
