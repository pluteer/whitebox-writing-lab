@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0WhiteboxLauncher.ps1"
if errorlevel 1 (
  echo Whitebox launcher failed with exit code %errorlevel%.
  pause
)
endlocal
