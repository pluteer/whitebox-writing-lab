@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0WhiteboxPortable.ps1"
if errorlevel 1 (
  echo Whitebox failed to start. Check logs\api-error.log
  pause
)
endlocal
